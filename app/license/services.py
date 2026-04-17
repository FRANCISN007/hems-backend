# app/license/service.py

import json
import os
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
from math import ceil

from app.license import schemas, models
from app.core.timezone import now_wat, to_wat
from loguru import logger


LICENSE_FILE = "license_status.json"


# ---------------------------------------------------
# SAVE LICENSE FILE (OFFLINE SUPPORT)
# ---------------------------------------------------
def save_license_file(data: dict):
    """Save license status to local JSON file (offline fallback)."""
    safe_data = {}

    for k, v in data.items():
        if isinstance(v, datetime):
            safe_data[k] = v.isoformat()
        else:
            safe_data[k] = v

    try:
        with open(LICENSE_FILE, "w") as f:
            json.dump(safe_data, f)
    except Exception as e:
        logger.error(f"Failed to save license file: {e}")


# ---------------------------------------------------
# LOAD LICENSE FILE
# ---------------------------------------------------
def load_license_file():
    """Load license status from local JSON file."""
    if not os.path.exists(LICENSE_FILE):
        return None

    try:
        with open(LICENSE_FILE, "r") as f:
            data = json.load(f)

        if data.get("expires_on"):
            data["expires_on"] = datetime.fromisoformat(data["expires_on"])

        return data

    except Exception as e:
        logger.error(f"Failed to load license file: {e}")
        return None


# ---------------------------------------------------
# CREATE LICENSE
# ---------------------------------------------------
def create_license_key(
    db: Session,
    data: schemas.LicenseCreate
) -> schemas.LicenseResponse:
    """Create new license key in DB."""
    new_license = models.LicenseKey(
        key=data.key,
        expiration_date=data.expiration_date,
        business_id=data.business_id,
        is_active=True,
    )

    db.add(new_license)
    db.commit()
    db.refresh(new_license)

    return schemas.LicenseResponse.from_orm(new_license)


# ---------------------------------------------------
# VERIFY LICENSE (UPDATED - WAT SAFE + WARNING)
# ---------------------------------------------------
from math import ceil
from app.core.timezone import now_wat, to_wat

def verify_license_key(db: Session, key: str, business_id: int) -> dict:
    """
    Verify license key for a business.
    - WAT timezone safe
    - Includes 7-day expiry warning
    - Returns consistent response structure
    """

    # -----------------------------
    # FETCH LICENSE
    # -----------------------------
    license_record = (
        db.query(models.LicenseKey)
        .filter(
            models.LicenseKey.key == key,
            models.LicenseKey.business_id == business_id,
            models.LicenseKey.is_active == True,
        )
        .first()
    )

    # -----------------------------
    # INVALID LICENSE
    # -----------------------------
    if not license_record:
        return {
            "valid": False,
            "expires_on": None,
            "message": "Invalid license key",
            "warning": True,
            "days_left": None
        }

    # -----------------------------
    # TIME HANDLING (WAT SAFE)
    # -----------------------------
    now = now_wat()
    expires_on = to_wat(license_record.expiration_date)

    # -----------------------------
    # EXPIRED LICENSE
    # -----------------------------
    if expires_on <= now:
        return {
            "valid": False,
            "expires_on": expires_on,
            "message": "License expired",
            "warning": True,
            "days_left": 0
        }

    # -----------------------------
    # CALCULATE DAYS LEFT (ACCURATE)
    # -----------------------------
    delta_seconds = (expires_on - now).total_seconds()
    days_left = ceil(delta_seconds / 86400)

    # -----------------------------
    # WARNING LOGIC
    # -----------------------------
    warning = days_left <= 7

    # -----------------------------
    # MESSAGE
    # -----------------------------
    message = (
        f"⚠️ License expires in {days_left} day(s). Please renew."
        if warning
        else "License valid"
    )

    # -----------------------------
    # RESPONSE
    # -----------------------------
    return {
        "valid": True,
        "expires_on": expires_on,
        "message": message,
        "warning": warning,
        "days_left": days_left
    }
