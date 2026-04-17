
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
from fastapi import Query
from datetime import date
from typing import Optional, List
from collections import defaultdict
from app.users.auth import get_current_user
from app.users.permissions import role_required  # 👈 permission helper
from app.users.models import User
from app.users import schemas as user_schemas

from app.database import get_db
from sqlalchemy.orm import Session, joinedload

from app.restpayment.models import  RestaurantSalePayment
from app.restaurant.models import RestaurantSale
from app.restpayment import models as restpayment_models
from app.restaurant import models as restaurant_models


from app.restpayment.schemas import RestaurantSaleDisplay, RestaurantSalePaymentDisplay, PaymentCreate

from app.restpayment.schemas import RestaurantSaleWithPaymentsDisplay, UpdatePaymentSchema
from app.restpayment.services import update_sale_status
from fastapi import Path
from app.core.timezone import now_wat

from app.core.timezone import now_wat
from app.core.tenant import resolve_business_id


router = APIRouter()

# app/restpayment/routes.py





@router.post("/sales/{sale_id}/payments", response_model=RestaurantSaleDisplay)
def add_payment_to_sale(
    sale_id: int,
    payment: PaymentCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # =========================
    # ✅ Resolve tenant context
    # =========================
    resolved_business_id = resolve_business_id(current_user, business_id)

    # =========================
    # ✅ Fetch sale (auto-filter still applies)
    # =========================
    sale = (
        db.query(RestaurantSale)
        .options(joinedload(RestaurantSale.payments))
        .filter(RestaurantSale.id == sale_id)
        .first()
    )

    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")

    # =========================
    # ⚠️ EXTRA SAFETY CHECK (important for super admin)
    # =========================
    if sale.business_id != resolved_business_id:
        raise HTTPException(
            status_code=403,
            detail="Sale does not belong to selected business"
        )

    # =========================
    # ✅ Validate payment date
    # =========================
    today_wat = now_wat().date()

    if payment.payment_date > today_wat:
        raise HTTPException(
            status_code=400,
            detail="Payment date cannot be in the future"
        )

    # =========================
    # ✅ Calculate balance
    # =========================
    total_paid = sum(
        p.amount_paid for p in sale.payments if not p.is_void
    )

    balance = (sale.total_amount or 0) - total_paid

    if payment.amount > balance:
        raise HTTPException(
            status_code=400,
            detail=f"Payment exceeds outstanding balance. Balance left: {balance}"
        )

    # =========================
    # ✅ Normalize bank
    # =========================
    bank_value = payment.bank.strip() if payment.bank else None

    if bank_value and bank_value.upper() in ("0", "NONE", "NULL", "NO BANK"):
        bank_value = None

    # =========================
    # ✅ Create payment
    # =========================
    new_payment = RestaurantSalePayment(
        sale_id=sale.id,
        business_id=resolved_business_id,  # 🔥 SUPER ADMIN SAFE
        amount_paid=payment.amount,
        payment_mode=payment.payment_mode.lower(),
        bank=bank_value,
        paid_by=payment.paid_by,
        payment_date=payment.payment_date,
        is_void=False,
        created_at=now_wat(),
        updated_at=now_wat()
    )

    db.add(new_payment)
    db.flush()

    # =========================
    # ✅ Update sale status
    # =========================
    update_sale_status(sale, db)

    db.commit()
    db.refresh(sale)

    # =========================
    # ✅ Compute totals
    # =========================
    sale.amount_paid = sum(
        p.amount_paid for p in sale.payments if not p.is_void
    )

    sale.balance = (sale.total_amount or 0) - sale.amount_paid

    return sale


@router.get("/sales/payments", response_model=dict)
def list_payments_with_items(
    sale_id: Optional[int] = None,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    location_id: Optional[int] = Query(None),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # =========================
    # ✅ Resolve tenant context
    # =========================
    resolved_business_id = resolve_business_id(current_user, business_id)

    # =========================
    # Base query (tenant auto-filter already applies)
    # =========================
    query = (
        db.query(restpayment_models.RestaurantSalePayment)
        .join(restaurant_models.RestaurantSale)
    )

    # =========================
    # FILTERS
    # =========================
    if sale_id:
        query = query.filter(restaurant_models.RestaurantSale.id == sale_id)

    if location_id:
        query = query.filter(
            restaurant_models.RestaurantSale.location_id == location_id
        )

    if start_date:
        query = query.filter(
            restpayment_models.RestaurantSalePayment.payment_date >= start_date
        )

    if end_date:
        query = query.filter(
            restpayment_models.RestaurantSalePayment.payment_date <= end_date
        )

    payments = query.order_by(
        restpayment_models.RestaurantSalePayment.payment_date.desc()
    ).all()

    # =========================
    # GROUP BY SALES
    # =========================
    sales_map = {}

    for p in payments:
        sale = p.sale
        if not sale:
            continue

        if sale.id not in sales_map:
            total_paid_for_sale = (
                db.query(func.coalesce(func.sum(
                    restpayment_models.RestaurantSalePayment.amount_paid
                ), 0))
                .filter(
                    restpayment_models.RestaurantSalePayment.sale_id == sale.id,
                    restpayment_models.RestaurantSalePayment.is_void == False
                )
                .scalar()
            )

            balance = float(sale.total_amount or 0) - float(total_paid_for_sale)

            status = (
                "unpaid" if total_paid_for_sale == 0 else
                "partial" if total_paid_for_sale < sale.total_amount else
                "paid"
            )

            sales_map[sale.id] = {
                "id": sale.id,
                "guest_name": sale.guest_name,
                "total_amount": float(sale.total_amount or 0),
                "amount_paid": float(total_paid_for_sale),
                "balance": balance,
                "payments": [],
                "status": status,
            }

        payment_dict = {
            "id": p.id,
            "sale_id": p.sale_id,
            "amount_paid": float(p.amount_paid or 0),
            "payment_mode": p.payment_mode,
            "bank": p.bank,
            "paid_by": p.paid_by,
            "is_void": p.is_void,
            "created_at": p.created_at,
            "payment_date": p.payment_date.isoformat() if p.payment_date else None,
            "balance": sales_map[sale.id]["balance"],
        }

        sales_map[sale.id]["payments"].append(payment_dict)

    # =========================
    # SUMMARY
    # =========================
    summary = {
        "total_sales": 0,
        "total_paid": 0,
        "total_due": 0,
        "total_cash": 0,
        "total_pos": 0,
        "total_transfer": 0,
        "banks": {}
    }

    for sale_data in sales_map.values():
        summary["total_sales"] += sale_data["total_amount"]
        summary["total_paid"] += sale_data["amount_paid"]
        summary["total_due"] += sale_data["balance"]

        for p in sale_data["payments"]:
            if p["is_void"]:
                continue

            amount = p["amount_paid"]
            mode = p["payment_mode"]
            bank = (p["bank"] or "").upper().strip()

            if mode == "cash":
                summary["total_cash"] += amount
            elif mode == "pos":
                summary["total_pos"] += amount
            elif mode == "transfer":
                summary["total_transfer"] += amount

            if bank:
                if bank not in summary["banks"]:
                    summary["banks"][bank] = {"pos": 0, "transfer": 0}

                if mode == "pos":
                    summary["banks"][bank]["pos"] += amount
                elif mode == "transfer":
                    summary["banks"][bank]["transfer"] += amount

    redisplay_sales = [
        s for s in sales_map.values()
        if s["balance"] > 0
    ]

    return {
        "sales": list(sales_map.values()),
        "summary": summary,
        "redisplay_sales": redisplay_sales
    }



from typing import List

from sqlalchemy import func



@router.put(
    "/sales/payments/{payment_id}",
    response_model=RestaurantSalePaymentDisplay
)
def update_payment(
    payment_id: int,
    payload: UpdatePaymentSchema,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # =========================
    # ✅ Resolve tenant context
    # =========================
    resolved_business_id = resolve_business_id(current_user, business_id)

    # =========================
    # ✅ Fetch payment (tenant-safe via auto filter)
    # =========================
    payment = (
        db.query(RestaurantSalePayment)
        .filter(RestaurantSalePayment.id == payment_id)
        .first()
    )

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # =========================
    # ⚠️ Extra safety check
    # =========================
    if payment.business_id != resolved_business_id:
        raise HTTPException(
            status_code=403,
            detail="Payment does not belong to selected business"
        )

    updated = False

    # =========================
    # AMOUNT
    # =========================
    if payload.amount_paid is not None:
        payment.amount_paid = payload.amount_paid
        updated = True

    # =========================
    # PAYMENT MODE
    # =========================
    if payload.payment_mode is not None:
        payment.payment_mode = payload.payment_mode.lower()
        updated = True

    # =========================
    # PAID BY
    # =========================
    if payload.paid_by is not None:
        payment.paid_by = payload.paid_by
        updated = True

    # =========================
    # BANK NORMALIZATION
    # =========================
    if payload.bank is not None:
        bank_value = str(payload.bank).strip()

        if bank_value.upper() in ("0", "NONE", "NULL", "", "NO BANK"):
            bank_value = None

        if payment.bank != bank_value:
            payment.bank = bank_value
            updated = True

    # =========================
    # PAYMENT DATE VALIDATION
    # =========================
    if payload.payment_date is not None:
        if payload.payment_date > date.today():
            raise HTTPException(
                status_code=400,
                detail="Payment date cannot be in the future"
            )

        payment.payment_date = payload.payment_date
        updated = True

    # =========================
    # SAVE CHANGES
    # =========================
    if updated:
        payment.updated_at = now_wat()

        db.add(payment)
        db.flush()

        # Update related sale status
        sale = (
            db.query(RestaurantSale)
            .filter(RestaurantSale.id == payment.sale_id)
            .first()
        )

        if sale:
            update_sale_status(sale, db)

        db.commit()

    db.refresh(payment)
    return payment


# ✅ Void a payment
# ✅ Void a payment (cancel transaction but keep history)

@router.put("/sales/payments/{payment_id}/void", response_model=dict)
def void_payment(
    payment_id: int,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # =========================
    # ✅ Resolve tenant context
    # =========================
    resolved_business_id = resolve_business_id(current_user, business_id)

    # =========================
    # ✅ Fetch payment
    # =========================
    payment = (
        db.query(RestaurantSalePayment)
        .filter(RestaurantSalePayment.id == payment_id)
        .first()
    )

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # =========================
    # ⚠️ Tenant safety check
    # =========================
    if payment.business_id != resolved_business_id:
        raise HTTPException(
            status_code=403,
            detail="Payment does not belong to selected business"
        )

    # =========================
    # ⚠️ Already voided check
    # =========================
    if payment.is_void:
        raise HTTPException(
            status_code=400,
            detail="Payment is already voided"
        )

    # =========================
    # ❌ VOID PAYMENT (soft delete)
    # =========================
    payment.is_void = True
    payment.updated_at = now_wat()

    db.add(payment)
    db.flush()

    # =========================
    # 🔄 Recalculate sale status
    # =========================
    sale = (
        db.query(RestaurantSale)
        .filter(RestaurantSale.id == payment.sale_id)
        .first()
    )

    if sale:
        update_sale_status(sale, db)

    db.commit()
    db.refresh(payment)

    return {
        "message": "Payment voided successfully",
        "payment_id": payment.id
    }

    

@router.delete("/sales/payments/{payment_id}", response_model=dict)
def delete_payment(
    payment_id: int = Path(..., description="The ID of the payment to delete"),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # =========================
    # ✅ Resolve tenant context
    # =========================
    resolved_business_id = resolve_business_id(current_user, business_id)

    # =========================
    # ✅ Fetch payment
    # =========================
    payment = (
        db.query(RestaurantSalePayment)
        .filter(RestaurantSalePayment.id == payment_id)
        .first()
    )

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # =========================
    # ⚠️ Tenant validation
    # =========================
    if payment.business_id != resolved_business_id:
        raise HTTPException(
            status_code=403,
            detail="Payment does not belong to selected business"
        )

    # =========================
    # ❌ Delete payment
    # =========================
    db.delete(payment)
    db.flush()

    # =========================
    # 🔄 Update sale status
    # =========================
    sale = (
        db.query(RestaurantSale)
        .filter(RestaurantSale.id == payment.sale_id)
        .first()
    )

    if sale:
        update_sale_status(sale, db)

    db.commit()

    return {"message": "Payment deleted successfully"}