from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy.sql import func

from app.database import get_db
from . import models, schemas
from app.users.schemas import UserDisplaySchema
from app.payments import models as payment_models
from app.users.permissions import role_required
from app.core.business import resolve_business_id

router = APIRouter()


# ---------------------------------------------------
# HELPER: Get Bank Scoped To Business
# ---------------------------------------------------
def get_business_bank(db: Session, bank_id: int, business_id: int):
    bank = db.query(models.Bank).filter(
        models.Bank.id == bank_id,
        models.Bank.business_id == business_id
    ).first()

    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    return bank



# ---------------------------------------------------
# CREATE BANK (SaaS CLEAN VERSION)
# ---------------------------------------------------
@router.post("/", response_model=schemas.BankDisplay)
def create_bank(
    bank: schemas.BankCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # -------------------------------
        # 1️⃣ Resolve business (CENTRALIZED SaaS)
        # -------------------------------
        effective_business_id = resolve_business_id(current_user, business_id)

        # -------------------------------
        # 2️⃣ Normalize bank name
        # -------------------------------
        bank_name = bank.name.strip().title()

        # -------------------------------
        # 3️⃣ Prevent duplicates (tenant-safe)
        # -------------------------------
        existing = (
            db.query(models.Bank)
            .filter(
                models.Bank.business_id == effective_business_id,
                models.Bank.name == bank_name
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Bank already exists for this business"
            )

        # -------------------------------
        # 4️⃣ Create bank
        # -------------------------------
        new_bank = models.Bank(
            name=bank_name,
            business_id=effective_business_id
        )

        db.add(new_bank)
        db.commit()
        db.refresh(new_bank)

        return new_bank

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create bank: {str(e)}"
        )





@router.get("/", response_model=List[schemas.BankDisplay])
def list_banks(
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["dashboard", "admin", "super_admin"])
    )
):
    try:
        # ✅ CENTRALIZED SaaS CONTROL
        effective_business_id = resolve_business_id(current_user, business_id)

        banks = (
            db.query(models.Bank)
            .filter(models.Bank.business_id == effective_business_id)
            .order_by(models.Bank.name.asc())
            .all()
        )

        return banks

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch banks: {str(e)}"
        )



# ---------------------------------------------------
# SIMPLE LIST (FOR DROPDOWNS)
# ---------------------------------------------------
@router.get("/simple")
def list_banks_simple(
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["dashboard", "admin", "super_admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" in roles and business_id:
        target_business_id = business_id
    else:
        target_business_id = current_user.business_id

    banks = db.query(
        models.Bank.id,
        models.Bank.name
    ).filter(
        models.Bank.business_id == target_business_id
    ).order_by(models.Bank.name).all()

    return [{"id": bank.id, "name": bank.name} for bank in banks]


# ---------------------------------------------------
# UPDATE BANK
# ---------------------------------------------------
@router.put("/{bank_id}", response_model=schemas.BankDisplay)
def update_bank(
    bank_id: int,
    bank: schemas.BankUpdate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "super_admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" in roles and business_id:
        target_business_id = business_id
    else:
        target_business_id = current_user.business_id

    bank_name = bank.name.strip().title()

    db_bank = db.query(models.Bank).filter(
        models.Bank.id == bank_id,
        models.Bank.business_id == target_business_id
    ).first()

    if not db_bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    duplicate = db.query(models.Bank).filter(
        models.Bank.business_id == target_business_id,
        models.Bank.name == bank_name,
        models.Bank.id != bank_id
    ).first()

    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="Bank name already exists for this business"
        )

    db_bank.name = bank_name

    db.commit()
    db.refresh(db_bank)

    return db_bank


# ---------------------------------------------------
# DELETE BANK
# ---------------------------------------------------
@router.delete("/{bank_id}")
def delete_bank(
    bank_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "super_admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" in roles and business_id:
        target_business_id = business_id
    else:
        target_business_id = current_user.business_id

    db_bank = db.query(models.Bank).filter(
        models.Bank.id == bank_id,
        models.Bank.business_id == target_business_id
    ).first()

    if not db_bank:
        raise HTTPException(status_code=404, detail="Bank not found")

    # Check if bank used in payments
    usage_count = db.query(payment_models.Payment).filter(
        payment_models.Payment.bank_id == bank_id
    ).count()

    if usage_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete bank '{db_bank.name}'. It has been used in {usage_count} payment(s)."
        )

    db.delete(db_bank)
    db.commit()

    return {"detail": "Bank deleted successfully"}
