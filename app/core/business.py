from typing import Optional
from fastapi import HTTPException


def resolve_business_id(current_user, business_id: Optional[int]) -> int:
    roles = [r.strip().lower() for r in current_user.roles] if current_user.roles else []

    # ✅ SUPER ADMIN
    if "super_admin" in roles:
        if business_id is None:
            raise HTTPException(
                status_code=400,
                detail="Super admin must provide business_id"
            )
        return business_id

    # ✅ NORMAL USER MUST HAVE BUSINESS
    if not current_user.business_id:
        raise HTTPException(
            status_code=400,
            detail="User not assigned to a business"
        )

    # ✅ IF business_id IS PROVIDED → VALIDATE IT
    if business_id is not None and business_id != current_user.business_id:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to access this business"
        )

    # ✅ DEFAULT → USE USER BUSINESS
    return current_user.business_id
