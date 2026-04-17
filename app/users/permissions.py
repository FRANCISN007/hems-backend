from fastapi import Depends, HTTPException, status
from app.users.auth import get_current_user
from app.users import schemas as user_schemas
from typing import List, Set


def role_required(allowed_roles: List[str], bypass_admin: bool = True):
    """
    Checks that the current_user has at least one of the allowed roles.
    If bypass_admin=True, users with 'admin' or 'super_admin' role automatically pass.
    """
    allowed_set: Set[str] = set(r.strip().lower() for r in (allowed_roles or []))

    def wrapper(current_user: user_schemas.UserDisplaySchema = Depends(get_current_user)):
        user_roles = set(r.strip().lower() for r in (current_user.roles or []))

        # 🔐 Bypass for admin and super_admin
        if bypass_admin and ("admin" in user_roles or "super_admin" in user_roles):
            return current_user

        # Check intersection with allowed roles
        if not user_roles.intersection(allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

        return current_user

    return wrapper
