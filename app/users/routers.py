from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext  # ✅ Add this
from fastapi import Body
from app.users.auth import authenticate_user, create_access_token, get_current_user
from app.database import get_db
from app.users import crud as user_crud, schemas # Correct import for user CRUD operations
from app.users import models as user_models
from app.business.models import Business
from app.business import models as business_models
from app.license.models import LicenseKey
from sqlalchemy import func

import os
from loguru import logger
import os

router = APIRouter()



ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

logger.add("app.log", rotation="500 MB", level="DEBUG")



#log_path = os.path.join(os.getenv("LOCALAPPDATA", "C:\\Temp"), "app.log")
#logger.add("C:/Users/KLOUNGE/Documents/app.log", rotation="500 MB", level="DEBUG")




pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Store your admin password securely (e.g., environment variable)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "supersecret")

@router.post("/register/")
def sign_up(
    user: schemas.UserSchema,
    current_user: user_models.User = Depends(get_current_user),  # ← NEW: get the logged-in user
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    - Super admin can register anyone without admin_password
    - Normal admin must provide valid admin_password
    """
    # Normalize username
    user.username = user.username.strip().lower()

    # Check duplicate username
    existing_user = user_crud.get_user_by_username(db, user.username)
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Determine if current user is super admin
    is_super_admin_caller = "super_admin" in (current_user.roles or "")

    # Enforce admin_password ONLY if caller is NOT super admin
    if not is_super_admin_caller:
        if not user.admin_password or user.admin_password != ADMIN_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin can register users. Invalid admin password."
            )

    # ------------------------------
    # Validate and attach business_id
    # ------------------------------
    business = None
    if "super_admin" not in user.roles:
        # Normal users and admins must have a business
        if not user.business_id:
            raise HTTPException(status_code=400, detail="User must belong to a business")

        business = db.query(business_models.Business).filter(
            business_models.Business.id == user.business_id
        ).first()

        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        if not business.is_license_active:
            raise HTTPException(status_code=403, detail="Business is inactive")

    # ------------------------------
    # Hash password and create user
    # ------------------------------
    hashed_password = pwd_context.hash(user.password)

    new_user = user_crud.create_user(
        db=db,
        user=user,
        hashed_password=hashed_password,
        business_id=business.id if business else None
    )

    return {
        "message": f"User {user.username} registered successfully",
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "roles": new_user.roles.split(","),
            "business_id": new_user.business_id
        }
    }



@router.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    username = form_data.username.strip()  # STRICT
    password = form_data.password

    user = authenticate_user(db, username, password)
    if not user:
        logger.warning(f"Authentication denied for username: {username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    roles = user.roles.split(",") if isinstance(user.roles, str) else user.roles
    roles = [r.strip().lower() for r in roles]
    is_super_admin = "super_admin" in roles

    business = None
    license_key = None
    business_id = None

    if not is_super_admin:
        if not user.business_id:
            raise HTTPException(status_code=403, detail="User must belong to a business")

        business = db.query(Business).filter(Business.id == user.business_id).first()
        if not business or not business.is_license_active:
            raise HTTPException(status_code=403, detail="Business is missing or inactive")

        license_key = (
            db.query(LicenseKey)
            .filter(
                LicenseKey.business_id == business.id,
                LicenseKey.is_active == True
            )
            .order_by(LicenseKey.expiration_date.desc())
            .first()
        )

        if not license_key:
            raise HTTPException(status_code=403, detail="No active license for this business")

        from datetime import datetime
        if license_key.expiration_date < datetime.utcnow():
            raise HTTPException(status_code=403, detail="Business license expired")

        business_id = business.id

    access_token = create_access_token(
        data={
            "sub": user.username,
            "business_id": business_id,
        }
    )

    logger.info(f"✅ User authenticated: {user.username} (Super Admin: {is_super_admin})")

    return {
        "id": user.id,
        "username": user.username,
        "roles": roles,
        
        # Added this single line for easy frontend access
        "business_name": business.name if business else None,

        "business": {
            "id": business.id if business else None,
            "name": business.name if business else None,
            "address": business.address if business else None,
            "phone": business.phone if business else None,
            "email": business.email if business else None,
        },

        "license": {
            "expiration_date": license_key.expiration_date if license_key else None,
            "is_active": license_key.is_active if license_key else None,
        },
        "access_token": access_token,
        "token_type": "bearer",
    }


# List users with tenant isolation
@router.get("/", response_model=list[schemas.UserDisplaySchema])
def list_all_users(
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    roles = set(current_user.roles)

    # ❌ Normal users cannot list users
    if not roles.intersection({"admin", "super_admin"}):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # ✅ Super admin → see all users
    if "super_admin" in roles:
        return user_crud.get_all_users(db)

    # ✅ Business admin → see only users in same business
    return user_crud.get_users_by_business(db, current_user.business_id)


# Reset user password — admin OR super_admin with tenant isolation
@router.put("/{username}/reset_password")
def reset_password(
    username: str,
    new_password: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    roles = set(current_user.roles)

    # ❌ Only admin or super_admin allowed
    if not roles.intersection({"admin", "super_admin"}):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ===============================
    # TENANT SECURITY CHECK
    # ===============================

    # Super admin → can reset ANY password
    if "super_admin" not in roles:
        # Admin → can reset ONLY:
        #   1. their own password
        #   2. users in same business
        if user.business_id != current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="You can only reset passwords for users in your business",
            )

    # ===============================
    # UPDATE PASSWORD
    # ===============================
    user.hashed_password = pwd_context.hash(new_password)
    db.commit()
    db.refresh(user)

    return {"message": f"Password for {username} has been reset"}



# ------------------- CURRENT USER -------------------
@router.get("/me", response_model=schemas.UserDisplaySchema)
def get_current_user_info(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns authenticated user info + business + license.
    Works for both super_admin and business users.
    """

    # Ensure roles is always a list
    roles = (
        current_user.roles.split(",")
        if isinstance(current_user.roles, str)
        else current_user.roles
    )

    business_name = None
    license_info = None

    # ===============================
    # FETCH BUSINESS NAME (if exists)
    # ===============================
    if current_user.business_id:
        business = db.query(Business).filter(Business.id == current_user.business_id).first()
        if business:
            business_name = business.name

            # ===============================
            # FETCH LICENSE
            # ===============================
            license_key = (
                db.query(LicenseKey)
                .filter(
                    LicenseKey.business_id == business.id,
                    LicenseKey.is_active == True,
                )
                .order_by(LicenseKey.expiration_date.desc())
                .first()
            )
            if license_key:
                license_info = {
                    "key": license_key.key,
                    "is_active": license_key.is_active,
                    "expiration_date": license_key.expiration_date,
                }

    # ===============================
    # RETURN CLEAN USER OBJECT
    # ===============================
    return schemas.UserDisplaySchema(
        id=current_user.id,
        username=current_user.username,
        roles=roles,
        business_id=current_user.business_id,
        business_name=business_name,
        license=license_info,
    )


# ------------------- UPDATE USER -------------------
@router.put("/{username}")
def update_user(
    username: str,
    updated_user: schemas.UserUpdateSchema,
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    # Only admin or super_admin can update users
    if not set(current_user.roles).intersection({"admin", "super_admin"}):
        logger.warning(f"Unauthorized update attempt by {current_user.username}")
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        logger.warning(f"User not found: {username}")
        raise HTTPException(status_code=404, detail="User not found")

    roles = set(current_user.roles)

    # -------------------------------
    # Admin restriction: only own business or self
    # -------------------------------
    if "super_admin" not in roles:
        if user.id != current_user.id and user.business_id != current_user.business_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot update users outside your business"
            )

    # -------------------------------
    # Update password if provided
    # -------------------------------
    if updated_user.password:
        user.hashed_password = pwd_context.hash(updated_user.password)

    # -------------------------------
    # Update roles
    # -------------------------------
    if updated_user.roles is not None:
        if "super_admin" in roles:
            # Super admin can assign any roles
            user.roles = ",".join(updated_user.roles)
        else:
            # Admin updating self → allow all roles except super_admin
            if user.id == current_user.id:
                filtered_roles = [r for r in updated_user.roles if r != "super_admin"]
                user.roles = ",".join(filtered_roles)

            # Admin updating others in their business → allow roles except super_admin
            elif user.business_id == current_user.business_id:
                filtered_roles = [r for r in updated_user.roles if r != "super_admin"]
                user.roles = ",".join(filtered_roles)
                logger.info(f"Admin {current_user.username} updated roles for {username} (super_admin role ignored)")

    # -------------------------------
    # Update other fields
    # -------------------------------
    for field, value in updated_user.dict(exclude_unset=True, exclude={"password", "roles"}).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    logger.info(f"User {username} updated successfully by {current_user.username}")

    return {"message": f"User {username} updated successfully"}



# ------------------- DELETE USER -------------------
@router.delete("/{username}")
def delete_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: schemas.UserDisplaySchema = Depends(get_current_user),
):
    username = username.strip().lower()

    roles = set(current_user.roles)

    # Only admin or super_admin can delete users
    if not roles.intersection({"admin", "super_admin"}):
        logger.warning(f"Unauthorized delete attempt by {current_user.username}")
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Prevent self-deletion
    if username == current_user.username:
        logger.warning(f"{current_user.username} attempted to delete themselves.")
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")

    user = user_crud.get_user_by_username(db, username)
    if not user:
        logger.warning(f"User not found: {username}")
        raise HTTPException(status_code=404, detail="User not found")

    # Admin restriction: can only delete users in their own business
    if "super_admin" not in roles:
        if user.business_id != current_user.business_id:
            logger.warning(f"Admin {current_user.username} attempted to delete user {username} outside their business")
            raise HTTPException(
                status_code=403,
                detail="Admins can only delete users within their own business"
            )

    db.delete(user)
    db.commit()
    logger.info(f"User {username} deleted successfully by {current_user.username}")
    return {"message": f"User {username} deleted successfully"}
