from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.hash import argon2
import os

from app.users.schemas import SuperAdminUpdate 
from app.database import get_db
from app.users import models
from app.users.schemas import SuperAdminCreate
from app.users.auth import get_password_hash

router = APIRouter()


def verify_admin_license_password(plain_password: str) -> bool:
    stored_hash = os.getenv("ADMIN_LICENSE_PASSWORD_HASH")
    if not stored_hash:
        return False
    try:
        return argon2.verify(plain_password, stored_hash)
    except Exception:
        return False


@router.post("/bootstrap-super-admin")
def bootstrap_super_admin(
    data: SuperAdminCreate,
    db: Session = Depends(get_db),
):
    """
    Create the FIRST super admin.

    Security rules:
    - Works ONLY if no super admin exists
    - Requires valid admin license password
    """

    # 1️⃣ Block if a super admin already exists
    existing_super_admin = (
        db.query(models.User)
        .filter(models.User.roles.contains("super_admin"))
        .first()
    )

    if existing_super_admin:
        raise HTTPException(
            status_code=403,
            detail="Super admin already exists",
        )

    # 2️⃣ Verify admin license password
    if not verify_admin_license_password(data.admin_license_password):
        raise HTTPException(
            status_code=403,
            detail="Invalid admin license password",
        )

    # 3️⃣ Create super admin user
    user = models.User(
        username=data.username,
        hashed_password=get_password_hash(data.password),
        roles="super_admin",
        business_id=None,  # root-level user
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Super admin created successfully"}





def verify_admin_license_password(plain_password: str) -> bool:
    stored_hash = os.getenv("ADMIN_LICENSE_PASSWORD_HASH")
    if not stored_hash:
        return False
    try:
        return argon2.verify(plain_password, stored_hash)
    except Exception:
        return False


@router.put("/update-super-admin-password")
def update_super_admin_password(
    data: SuperAdminUpdate,
    db: Session = Depends(get_db),
):
    """
    Update an existing Super Admin's password.

    Security rules:
    - Requires valid Admin License password
    - Only updates users with role 'super_admin'
    """

    # 1️⃣ Verify Admin License password first
    if not verify_admin_license_password(data.admin_license_password):
        raise HTTPException(
            status_code=403,
            detail="Invalid Admin License password",
        )

    # 2️⃣ Fetch the Super Admin user
    super_admin = (
        db.query(models.User)
        .filter(models.User.username == data.username)
        .filter(models.User.roles.contains("super_admin"))
        .first()
    )

    if not super_admin:
        raise HTTPException(
            status_code=404,
            detail=f"Super Admin '{data.username}' not found",
        )

    # 3️⃣ Hash the new password and update
    super_admin.hashed_password = get_password_hash(data.new_password)
    db.commit()
    db.refresh(super_admin)

    return {"message": f"Password for Super Admin '{data.username}' updated successfully"}
