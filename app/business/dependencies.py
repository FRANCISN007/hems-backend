# app/users/auth.py (fully rewritten get_current_business - now uses dynamic license check)
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.users.auth import get_current_user
from app.business.models import Business


def get_current_business(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Central SaaS guard:
    - Regular users: must belong to a business with active license
    - Super admins: exempted from business/license checks
    """

    # 🔹 Super admin bypass
    if "super_admin" in getattr(current_user, "roles", []):
        return None  # super admin does not need a business

    # 🔹 Regular user: must have business_id
    business_id = getattr(current_user, "business_id", None)
    if not business_id:
        raise HTTPException(status_code=400, detail="User does not belong to any business")

    # Fetch business
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # 🔹 Check license dynamically
    if not business.is_license_active(db):
        raise HTTPException(status_code=403, detail="Business license is inactive or expired")

    return business