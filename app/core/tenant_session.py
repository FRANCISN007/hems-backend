from sqlalchemy.orm import Session
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria
from fastapi import HTTPException

from app.core.tenant import get_current_business
from app.core.mixins import BusinessMixin


@event.listens_for(Session, "do_orm_execute")
def _add_tenant_filter(execute_state):

    # ✅ Only apply to SELECT queries
    if not execute_state.is_select:
        return

    business_id = get_current_business()

    # =========================
    # 🚫 BLOCK INVALID STATES
    # =========================
    if business_id == "REQUIRED":
        raise HTTPException(
            status_code=400,
            detail="Super admin must provide business_id"
        )

    if business_id == "INVALID":
        raise HTTPException(
            status_code=400,
            detail="Invalid business_id"
        )

    # =========================
    # ⚠️ NO TENANT CONTEXT
    # =========================
    if business_id is None:
        # Optional: allow public queries or block
        return

    # =========================
    # ✅ APPLY TENANT FILTER
    # =========================
    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            BusinessMixin,
            lambda cls: cls.business_id == business_id,
            include_aliases=True,
        )
    )
