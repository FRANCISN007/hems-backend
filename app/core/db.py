from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.tenant import set_current_business
from app.database import get_db
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema

def db_dependency(
    current_user: UserDisplaySchema = Depends(get_current_user),
):
    """
    Provides a DB session and sets the current tenant automatically.

    - Business users → tenant isolation enabled
    - Super admin (business_id=None) → tenant filter bypass
    """
    # Set tenant context
    set_current_business(current_user.business_id if current_user.business_id else None)

    # Use yield from get_db() so FastAPI handles dependency lifecycle
    try:
        yield from get_db()
    finally:
        # No need to manually close, get_db() already closes the session
        pass
