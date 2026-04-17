from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import func


from app.database import get_db
from app.users import crud, schemas as user_schemas
from app.business.models import Business  # New import for business info
from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(db: Session, username: str, password: str):
    user = crud.get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode JWT
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        business_id_raw = payload.get("business_id")
        business_id_from_token: Optional[int] = int(business_id_raw) if business_id_raw is not None else None
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Load user from DB
    user = crud.get_user_by_username(db, username)
    if not user:
        raise credentials_exception

    # Normalize roles
    roles = [r.strip().lower() for r in user.roles.split(",")] if user.roles else ["user"]

    # Determine effective business_id
    if "super_admin" not in roles:
        if user.business_id is None:
            raise HTTPException(
                status_code=403,
                detail="Current admin user has no business assigned"
            )

        # Use business_id from token if valid, otherwise DB value
        effective_business_id = business_id_from_token or int(user.business_id)

        # Ensure it matches DB
        if int(user.business_id) != effective_business_id:
            raise HTTPException(
                status_code=403,
                detail="User does not belong to this business"
            )

        # Confirm business exists and is active
        business = db.query(Business).filter(Business.id == effective_business_id).first()
        if not business or not business.is_license_active:
            raise HTTPException(status_code=403, detail="Business not found or inactive")

    else:
        # Super admin has no business
        business = None
        effective_business_id = None

    # Return schema
    return user_schemas.UserDisplaySchema(
        id=user.id,
        username=user.username,
        roles=roles,
        business_id=effective_business_id,  # guaranteed int or None
        business_name=business.name if business else None
    )
