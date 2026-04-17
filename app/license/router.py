# app/license/router.py
from fastapi import APIRouter, Depends, HTTPException, Form, status
from sqlalchemy.orm import Session
from loguru import logger

from datetime import datetime, date, time
from typing import Optional, Dict, Any
from sqlalchemy import func
from datetime import datetime, timedelta
import os

from datetime import timedelta
from app.core.timezone import now_wat, to_wat  # ✅ import your helper


from math import ceil
from app.core.timezone import now_wat, to_wat




from app.database import get_db
from app.license import schemas, services, models as license_models
from app.business.models import Business
from app.superadmin.passwords import verify_password
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema

from dotenv import load_dotenv
load_dotenv()  # loads .env file

router = APIRouter()

logger.add("app.log", rotation="500 MB", level="DEBUG")

# Env config
ADMIN_LICENSE_PASSWORD_HASH = os.getenv("ADMIN_LICENSE_PASSWORD_HASH")
LICENSE_FILE = "license_status.json"


@router.post("/generate", response_model=schemas.LicenseResponse, status_code=201)
def generate_license_key(
    license_password: str = Form(...),
    key: str = Form(...),
    duration_days: int = Form(..., gt=0, description="Duration in days"),
    business_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    """
    Generate a new license key (super admin only).
    """
    if "super_admin" not in current_user.roles:
        raise HTTPException(403, "Only super admin can generate license keys")

    if not ADMIN_LICENSE_PASSWORD_HASH:
        raise HTTPException(500, "Admin password not configured")

    if not verify_password(license_password, ADMIN_LICENSE_PASSWORD_HASH):
        raise HTTPException(403, "Invalid license password")

    # Validate business exists
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(404, "Business not found")

    
    expiration_date = now_wat() + timedelta(days=duration_days)

    new_license = services.create_license_key(
        db,
        schemas.LicenseCreate(
            key=key,
            expiration_date=expiration_date,
            business_id=business_id,
        )
    )

    # Save offline fallback
    services.save_license_file({
        "valid": True,
        "expires_on": new_license.expiration_date,
    })

    return new_license


@router.get("/verify/{key}/{business_id}", response_model=schemas.LicenseStatusResponse)
def verify_license(
    key: str,
    business_id: int,
    db: Session = Depends(get_db),
):
    """
    Verify license key for a specific business (public endpoint).
    """
    result = services.verify_license_key(db, key, business_id)

    # Save fallback
    services.save_license_file({
        "valid": result["valid"],
        "expires_on": result.get("expires_on"),
    })

    if not result["valid"]:
        raise HTTPException(400, result["message"])

    return result



from math import ceil
from app.core.timezone import now_wat, to_wat

from math import ceil
from app.core.timezone import now_wat, to_wat

@router.get("/check", response_model=schemas.LicenseStatusResponse)
def check_license_status(
    current_user: UserDisplaySchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check license status with accurate 7-day warning (WAT safe).
    """

    # -----------------------------
    # SUPER ADMIN
    # -----------------------------
    if "super_admin" in current_user.roles:
        return {
            "valid": True,
            "expires_on": None,
            "message": "Super admin - no license required",
            "warning": False,
            "days_left": None
        }

    # -----------------------------
    # VALIDATE BUSINESS
    # -----------------------------
    if not current_user.business_id:
        raise HTTPException(403, "User does not belong to any business")

    # -----------------------------
    # GET LICENSE
    # -----------------------------
    license_record = (
        db.query(license_models.LicenseKey)
        .filter(
            license_models.LicenseKey.business_id == current_user.business_id,
            license_models.LicenseKey.is_active == True,
        )
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    if not license_record:
        return {
            "valid": False,
            "expires_on": None,
            "message": "No active license found",
            "warning": True,
            "days_left": None
        }

    # -----------------------------
    # TIME (WAT SAFE)
    # -----------------------------
    now = now_wat()
    expires_on = to_wat(license_record.expiration_date)

    # -----------------------------
    # EXPIRED
    # -----------------------------
    if expires_on < now:
        return {
            "valid": False,
            "expires_on": expires_on,
            "message": "License expired",
            "warning": True,
            "days_left": 0
        }

    # -----------------------------
    # ACCURATE DAYS LEFT
    # -----------------------------
    delta_seconds = (expires_on - now).total_seconds()
    days_left = ceil(delta_seconds / 86400)  # ✅ FIXED HERE

    # -----------------------------
    # WARNING LOGIC
    # -----------------------------
    warning = days_left <= 7

    # -----------------------------
    # MESSAGE
    # -----------------------------
    if warning:
        message = f"⚠️ License expires in {days_left} day(s). Please renew."
    else:
        message = "License valid"

    data = {
        "valid": True,
        "expires_on": expires_on,
        "message": message,
        "warning": warning,
        "days_left": days_left
    }

    services.save_license_file(data)

    return data

