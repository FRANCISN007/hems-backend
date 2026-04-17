# app/users/crud.py
from typing import Optional
from sqlalchemy.orm import Session
from app.business.models import Business
from app.users.models import User
from app.users import schemas as user_schema
from sqlalchemy import func


# ------------------- CREATE USER -------------------
def create_user(
    db: Session,
    user: user_schema.UserSchema,
    hashed_password: str,
    business_id: Optional[int] = None
):
    """
    Create a new user in the database.
    Supports optional business_id (None for super_admin).
    """
    roles_str = ",".join(user.roles) if user.roles else "user"
    new_user = User(
        username=user.username.strip().lower(),
        hashed_password=hashed_password,
        roles=roles_str,
        business_id=business_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# ------------------- GET USER (CASE-SENSITIVE) -------------------
def get_user_by_username(db: Session, username: str):
    return (
        db.query(User)
        .filter(User.username == username.strip())
        .first()
    )



def get_all_users(db: Session, skip: int = 0, limit: int = 50):
    users = db.query(User).offset(skip).limit(limit).all()

    result = []

    for user in users:
        roles = user.roles.split(",") if user.roles else ["user"]

        # 🔹 Fetch business name using business_id
        business = None
        if user.business_id:
            business = db.query(Business).filter(Business.id == user.business_id).first()

        result.append(
            user_schema.UserDisplaySchema(
                id=user.id,
                username=user.username,
                roles=roles,
                business_id=user.business_id,
                business_name=business.name if business else None,  # ← NEW
            )
        )

    return result


def get_users_by_business(db: Session, business_id: int, skip: int = 0, limit: int = 50):
    users = (
        db.query(User)
        .filter(User.business_id == business_id)
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []

    for user in users:
        roles = user.roles.split(",") if user.roles else ["user"]

        # Fetch business name
        business = db.query(Business).filter(Business.id == user.business_id).first()

        result.append(
            user_schema.UserDisplaySchema(
                id=user.id,
                username=user.username,
                roles=roles,
                business_id=user.business_id,
                business_name=business.name if business else None,
            )
        )

    return result


# ------------------- UPDATE USER -------------------
def update_user(
    db: Session,
    username: str,
    updated_user: user_schema.UserUpdateSchema,
    hashed_password: Optional[str] = None,
):
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if not user:
        return None

    if hashed_password:
        user.hashed_password = hashed_password

    if updated_user.roles:
        user.roles = ",".join(updated_user.roles)

    if updated_user.business_id is not None:
        user.business_id = updated_user.business_id

    db.commit()
    db.refresh(user)
    return user


# ------------------- DELETE USER -------------------
def delete_user_by_username(db: Session, username: str):
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False
