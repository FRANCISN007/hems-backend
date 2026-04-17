from contextvars import ContextVar
from typing import Optional
from fastapi import HTTPException

# ----------------------------
# CONTEXTVAR: holds current business per request
# ----------------------------
_current_business_id: ContextVar[Optional[int]] = ContextVar("current_business_id", default=None)


def set_current_business(business_id: Optional[int]):
    """Set the current business ID for the request"""
    _current_business_id.set(business_id)


def get_current_business() -> Optional[int]:
    """Get the current business ID for the request"""
    return _current_business_id.get()


def resolve_business_id(current_user, business_id: Optional[int]) -> int:
    """
    Determine the effective business_id for the request.

    Rules:
    - Super admin must explicitly provide a business_id (override)
    - Normal users always use their assigned business_id
    """

    # ✅ Normalize roles (handles BOTH string and list)
    if isinstance(current_user.roles, str):
        roles = [r.strip().lower() for r in current_user.roles.split(",")]
    elif isinstance(current_user.roles, list):
        roles = [r.strip().lower() for r in current_user.roles]
    else:
        roles = []

    # =========================
    # 👑 SUPER ADMIN
    # =========================
    if "super_admin" in roles:
        if business_id is None:
            raise HTTPException(
                status_code=400,
                detail="Super admin must provide business_id"
            )
        return business_id

    # =========================
    # 👤 NORMAL USER
    # =========================
    if not current_user.business_id:
        raise HTTPException(
            status_code=400,
            detail="User not assigned to a business"
        )

    return current_user.business_id
