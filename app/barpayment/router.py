from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from sqlalchemy.sql import func
from datetime import date, timedelta
from typing import Optional, List
from sqlalchemy import func
from app.database import get_db
from app.users.auth import get_current_user
from app.users.permissions import role_required  # 👈 permission helper
from . import models, schemas
from app.bar.models import BarSale
from app.barpayment.models import  BarPayment
from app.barpayment import models as barpayment_models
from app.barpayment import schemas as barpayment_schemas
from app.users import schemas as user_schemas
from app.bar import models as bar_models
from app.core.business import resolve_business_id





router = APIRouter()

# ----------------------------
# Create Bar Payment (Multi-Tenant)
# ----------------------------
@router.post("/", response_model=schemas.BarPaymentDisplay)
def create_bar_payment(
    payment: schemas.BarPaymentCreate,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch sale (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .filter(
                bar_models.BarSale.id == payment.bar_sale_id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Bar sale not found")

        # ------------------------------
        # 3️⃣ Validate payment date
        # ------------------------------
        payment_date = payment.date_paid or date.today()

        if isinstance(payment_date, str):
            try:
                payment_date = datetime.fromisoformat(payment_date).date()
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid payment date format"
                )

        if payment_date > date.today():
            raise HTTPException(
                status_code=400,
                detail="Payment date cannot be in the future"
            )

        # ------------------------------
        # 4️⃣ Validate amount
        # ------------------------------
        if payment.amount_paid <= 0:
            raise HTTPException(
                status_code=400,
                detail="Amount must be greater than zero"
            )

        # ------------------------------
        # 5️⃣ Create payment (tenant-safe)
        # ------------------------------
        db_payment = barpayment_models.BarPayment(
            bar_sale_id=payment.bar_sale_id,
            amount_paid=payment.amount_paid,
            payment_method=payment.payment_method,
            bank=payment.bank,
            note=payment.note,
            date_paid=payment_date,
            created_by=current_user.username,
            status="active",
            business_id=business_id   # ✅ CRITICAL
        )

        db.add(db_payment)
        db.flush()

        # ------------------------------
        # 6️⃣ Recalculate totals (tenant-safe)
        # ------------------------------
        total_paid = (
            db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
            .filter(
                barpayment_models.BarPayment.bar_sale_id == payment.bar_sale_id,
                barpayment_models.BarPayment.business_id == business_id,
                barpayment_models.BarPayment.status == "active"
            )
            .scalar()
        )

        total_amount = float(sale.total_amount or 0)
        balance_due = total_amount - float(total_paid or 0)

        # ------------------------------
        # 7️⃣ Determine status
        # ------------------------------
        if total_paid == 0:
            status = "unpaid"
        elif total_paid < total_amount:
            status = "part payment"
        else:
            status = "fully paid"

        # ✅ keep sale status in sync
        sale.status = status

        db.commit()
        db.refresh(db_payment)

        # ------------------------------
        # 8️⃣ Response
        # ------------------------------
        return {
            "id": db_payment.id,
            "bar_sale_id": db_payment.bar_sale_id,
            "sale_amount": total_amount,
            "amount_paid": float(db_payment.amount_paid),
            "balance_due": float(balance_due),
            "payment_method": db_payment.payment_method,
            "bank": db_payment.bank,
            "note": db_payment.note,
            "date_paid": db_payment.date_paid,
            "created_by": db_payment.created_by,
            "status": status,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create bar payment: {str(e)}"
        )




@router.get("/")
def list_bar_payments(
    bar_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (STANDARD ✅)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Base query (tenant-safe)
        # ------------------------------
        query = (
            db.query(barpayment_models.BarPayment)
            .join(bar_models.BarSale,
                  bar_models.BarSale.id == barpayment_models.BarPayment.bar_sale_id)
            .filter(barpayment_models.BarPayment.business_id == business_id)
            .order_by(barpayment_models.BarPayment.date_paid.desc())
        )

        # ------------------------------
        # 3️⃣ Filters
        # ------------------------------
        if bar_id:
            query = query.filter(bar_models.BarSale.bar_id == bar_id)

        if start_date and not end_date:
            end_date = date.today()

        if start_date:
            query = query.filter(
                func.date(barpayment_models.BarPayment.date_paid) >= start_date
            )

        if end_date:
            query = query.filter(
                func.date(barpayment_models.BarPayment.date_paid) <= end_date
            )

        payments = query.all()

        # ------------------------------
        # 4️⃣ Preload sales (tenant-safe)
        # ------------------------------
        sale_ids = {p.bar_sale_id for p in payments}

        sales_map = {
            s.id: s for s in db.query(bar_models.BarSale).filter(
                bar_models.BarSale.id.in_(sale_ids),
                bar_models.BarSale.business_id == business_id
            ).all()
        }

        # ------------------------------
        # 5️⃣ Aggregations
        # ------------------------------
        response = []

        total_sales = 0.0
        total_paid_all = 0.0
        total_due_all = 0.0

        total_cash = 0.0
        total_pos = 0.0
        total_transfer = 0.0

        processed_sales = set()
        bank_summary = {}

        # ------------------------------
        # 6️⃣ Loop
        # ------------------------------
        for p in payments:
            sale = sales_map.get(p.bar_sale_id)
            if not sale:
                continue

            # 🔹 total paid per sale (tenant-safe)
            total_paid_for_sale = (
                db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
                .filter(
                    barpayment_models.BarPayment.bar_sale_id == sale.id,
                    barpayment_models.BarPayment.business_id == business_id,
                    barpayment_models.BarPayment.status == "active"
                )
                .scalar()
            )

            sale_total = float(sale.total_amount or 0)
            balance_due = sale_total - float(total_paid_for_sale or 0)

            # 🔹 Count sale once
            if sale.id not in processed_sales:
                total_sales += sale_total
                total_due_all += balance_due
                processed_sales.add(sale.id)

            # 🔹 Active payments only
            if p.status == "active":
                amt = float(p.amount_paid or 0)
                total_paid_all += amt

                method = (p.payment_method or "").lower()

                if method == "cash":
                    total_cash += amt
                elif method in ["pos", "card"]:
                    total_pos += amt
                elif method == "transfer":
                    total_transfer += amt

                # 🔹 Bank summary
                bank = (p.bank or "").strip().upper()
                if bank:
                    if bank not in bank_summary:
                        bank_summary[bank] = {"pos": 0.0, "transfer": 0.0}

                    if method in ["pos", "card"]:
                        bank_summary[bank]["pos"] += amt
                    elif method == "transfer":
                        bank_summary[bank]["transfer"] += amt

            # 🔹 Sale status
            if total_paid_for_sale == 0:
                sale_status = "unpaid"
            elif total_paid_for_sale < sale_total:
                sale_status = "part payment"
            else:
                sale_status = "fully paid"

            row_status = "voided payment" if p.status == "voided" else sale_status

            response.append({
                "id": p.id,
                "bar_sale_id": p.bar_sale_id,
                "sale_amount": sale_total,
                "amount_paid": float(p.amount_paid or 0),
                "cumulative_paid": float(total_paid_for_sale or 0),
                "balance_due": balance_due,
                "payment_method": p.payment_method,
                "bank": p.bank,
                "note": p.note,
                "date_paid": p.date_paid,
                "created_by": p.created_by,
                "status": row_status
            })

        # ------------------------------
        # 7️⃣ Final response
        # ------------------------------
        return {
            "payments": response,
            "summary": {
                "total_sales": total_sales,
                "total_paid": total_paid_all,
                "total_due": total_due_all,
                "total_cash": total_cash,
                "total_pos": total_pos,
                "total_transfer": total_transfer,
                "banks": bank_summary
            },
            "filters": {
                "bar_id": bar_id,
                "start_date": start_date,
                "end_date": end_date,
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve bar payments: {str(e)}"
        )



from fastapi import Query

@router.get("/outstanding", response_model=schemas.BarOutstandingSummary)
def list_outstanding_payments(
    bar_id: Optional[int] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (STANDARD ✅)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch sales (tenant-safe)
        # ------------------------------
        sales_query = db.query(bar_models.BarSale).filter(
            bar_models.BarSale.business_id == business_id
        )

        if bar_id:
            sales_query = sales_query.filter(
                bar_models.BarSale.bar_id == bar_id
            )

        sales = sales_query.all()

        # ------------------------------
        # 3️⃣ Process outstanding
        # ------------------------------
        results = []
        total_due = 0.0

        for sale in sales:
            total_paid = (
                db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
                .filter(
                    barpayment_models.BarPayment.bar_sale_id == sale.id,
                    barpayment_models.BarPayment.business_id == business_id,
                    barpayment_models.BarPayment.status == "active"
                )
                .scalar()
            )

            sale_total = float(sale.total_amount or 0)
            total_paid = float(total_paid or 0)
            balance_due = sale_total - total_paid

            if balance_due > 0:
                # 🔹 Determine status
                if total_paid == 0:
                    payment_status = "unpaid"
                elif total_paid < sale_total:
                    payment_status = "part payment"
                else:
                    payment_status = "fully paid"

                results.append({
                    "bar_sale_id": sale.id,
                    "bar_id": sale.bar_id,
                    "sale_amount": sale_total,
                    "amount_paid": total_paid,
                    "balance_due": balance_due,
                    "status": payment_status
                })

                total_due += balance_due

        # ------------------------------
        # 4️⃣ Response
        # ------------------------------
        return {
            "total_entries": len(results),
            "total_due": total_due,
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch outstanding payments: {str(e)}"
        )




@router.put("/{payment_id}", response_model=schemas.BarPaymentDisplay)
def update_bar_payment(
    payment_id: int,
    update_data: schemas.BarPaymentUpdate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch payment (tenant-safe)
        # ------------------------------
        payment = (
            db.query(barpayment_models.BarPayment)
            .filter(
                barpayment_models.BarPayment.id == payment_id,
                barpayment_models.BarPayment.business_id == business_id,
                barpayment_models.BarPayment.status == "active"
            )
            .first()
        )

        if not payment:
            raise HTTPException(status_code=404, detail="Active payment not found")

        # ------------------------------
        # 3️⃣ Apply updates
        # ------------------------------
        if update_data.amount_paid is not None:
            payment.amount_paid = update_data.amount_paid

        if update_data.payment_method is not None:
            payment.payment_method = update_data.payment_method

        if update_data.bank is not None:
            payment.bank = update_data.bank

        if update_data.note is not None:
            payment.note = update_data.note

        db.commit()
        db.refresh(payment)

        # ------------------------------
        # 4️⃣ Fetch sale (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .filter(
                bar_models.BarSale.id == payment.bar_sale_id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Bar sale not found")

        # ------------------------------
        # 5️⃣ Recalculate totals
        # ------------------------------
        total_paid = (
            db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
            .filter(
                barpayment_models.BarPayment.bar_sale_id == sale.id,
                barpayment_models.BarPayment.business_id == business_id,
                barpayment_models.BarPayment.status == "active"
            )
            .scalar()
        )

        sale_total = float(sale.total_amount or 0)
        total_paid = float(total_paid or 0)
        balance_due = sale_total - total_paid

        # ------------------------------
        # 6️⃣ Determine status
        # ------------------------------
        if total_paid == 0:
            status = "unpaid"
        elif total_paid < sale_total:
            status = "part payment"
        else:
            status = "fully paid"

        # ------------------------------
        # 7️⃣ Response
        # ------------------------------
        return {
            "id": payment.id,
            "bar_sale_id": payment.bar_sale_id,
            "sale_amount": sale_total,
            "amount_paid": float(payment.amount_paid or 0),
            "balance_due": balance_due,
            "payment_method": payment.payment_method,
            "bank": payment.bank,
            "note": payment.note,
            "date_paid": payment.date_paid,
            "created_by": payment.created_by,
            "status": status,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update payment: {str(e)}"
        )



@router.put("/{payment_id}/void", response_model=schemas.BarPaymentDisplay)
def void_bar_payment(
    payment_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch payment (tenant-safe)
        # ------------------------------
        payment = (
            db.query(barpayment_models.BarPayment)
            .filter(
                barpayment_models.BarPayment.id == payment_id,
                barpayment_models.BarPayment.business_id == business_id,
                barpayment_models.BarPayment.status == "active"
            )
            .first()
        )

        if not payment:
            raise HTTPException(status_code=404, detail="Active payment not found")

        # ------------------------------
        # 3️⃣ Void payment
        # ------------------------------
        payment.status = "voided"
        db.commit()
        db.refresh(payment)

        # ------------------------------
        # 4️⃣ Fetch related sale (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .filter(
                bar_models.BarSale.id == payment.bar_sale_id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Related bar sale not found")

        # ------------------------------
        # 5️⃣ Recalculate totals (exclude voided)
        # ------------------------------
        total_paid = (
            db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
            .filter(
                barpayment_models.BarPayment.bar_sale_id == sale.id,
                barpayment_models.BarPayment.business_id == business_id,
                barpayment_models.BarPayment.status == "active"
            )
            .scalar()
        )

        sale_total = float(sale.total_amount or 0)
        total_paid = float(total_paid or 0)
        balance_due = sale_total - total_paid

        # ------------------------------
        # 6️⃣ Determine sale status
        # ------------------------------
        if total_paid == 0:
            payment_status = "unpaid"
        elif total_paid < sale_total:
            payment_status = "part payment"
        else:
            payment_status = "fully paid"

        # ------------------------------
        # 7️⃣ Response
        # ------------------------------
        return {
            "id": payment.id,
            "bar_sale_id": payment.bar_sale_id,
            "sale_amount": sale_total,
            "amount_paid": float(payment.amount_paid or 0),  # this voided payment
            "balance_due": balance_due,
            "payment_method": payment.payment_method,
            "bank": payment.bank,
            "note": payment.note,
            "date_paid": payment.date_paid,
            "created_by": payment.created_by,
            "status": "voided"  # explicit
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to void payment: {str(e)}"
        )




@router.get("/payment-status")
def get_bar_payment_status(
    bar_id: Optional[int] = Query(None, description="Filter by bar ID"),
    status: Optional[str] = Query(
        None,
        description="Filter by status: fully paid, part payment, pending, voided payment"
    ),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Base query (tenant-safe)
        # ------------------------------
        query = (
            db.query(barpayment_models.BarPayment)
            .join(bar_models.BarSale,
                  bar_models.BarSale.id == barpayment_models.BarPayment.bar_sale_id)
            .filter(barpayment_models.BarPayment.business_id == business_id)
        )

        # ------------------------------
        # 3️⃣ Filters
        # ------------------------------
        if bar_id:
            query = query.filter(bar_models.BarSale.bar_id == bar_id)

        if start_date:
            query = query.filter(
                bar_models.BarSale.sale_date >= start_date
            )

        if end_date:
            query = query.filter(
                bar_models.BarSale.sale_date <= end_date
            )

        payments = query.all()

        # ------------------------------
        # 4️⃣ Preload sales (tenant-safe)
        # ------------------------------
        sale_ids = {p.bar_sale_id for p in payments}

        sales_map = {
            s.id: s for s in db.query(bar_models.BarSale).filter(
                bar_models.BarSale.id.in_(sale_ids),
                bar_models.BarSale.business_id == business_id
            ).all()
        }

        # ------------------------------
        # 5️⃣ Process results
        # ------------------------------
        results = []

        for payment in payments:
            sale = sales_map.get(payment.bar_sale_id)
            if not sale:
                continue

            sale_total = float(sale.total_amount or 0)

            # 🔹 total active payments for this sale
            total_paid = (
                db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
                .filter(
                    barpayment_models.BarPayment.bar_sale_id == sale.id,
                    barpayment_models.BarPayment.business_id == business_id,
                    barpayment_models.BarPayment.status == "active"
                )
                .scalar()
            )

            total_paid = float(total_paid or 0)

            # 🔹 determine status
            if payment.status == "voided":
                payment_status = "voided payment"
            elif total_paid == 0:
                payment_status = "pending"
            elif total_paid < sale_total:
                payment_status = "part payment"
            else:
                payment_status = "fully paid"

            # 🔹 apply filter
            if status and payment_status.lower() != status.lower():
                continue

            results.append({
                "payment_id": payment.id,
                "bar_sale_id": sale.id,
                "bar_id": sale.bar_id,
                "amount_due": sale_total,
                "amount_paid": float(payment.amount_paid or 0),
                "cumulative_paid": total_paid,
                "balance_due": sale_total - total_paid,
                "payment_status": payment_status,
                "date_paid": payment.date_paid,
                "payment_method": payment.payment_method,
                "created_by": payment.created_by,
            })

        return results

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch payment status: {str(e)}"
        )





@router.delete("/{payment_id}", response_model=dict)
def delete_bar_payment(
    payment_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch payment (tenant-safe)
        # ------------------------------
        payment = (
            db.query(barpayment_models.BarPayment)
            .filter(
                barpayment_models.BarPayment.id == payment_id,
                barpayment_models.BarPayment.business_id == business_id
            )
            .first()
        )

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # ------------------------------
        # 3️⃣ Delete payment
        # ------------------------------
        db.delete(payment)
        db.commit()

        return {
            "detail": f"Payment with ID {payment_id} has been deleted",
            "payment_id": payment_id,
            "business_id": business_id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete payment: {str(e)}"
        )
