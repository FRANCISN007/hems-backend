from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
from app.database import get_db
from app.events import models as event_models
from app.eventpayment import models as eventpayment_models, schemas as eventpayment_schemas
from app.users import schemas as user_schemas
from app.users.auth import get_current_user
from app.users.permissions import role_required  # 👈 permission helper
from typing import List
from sqlalchemy import and_
from datetime import datetime, timedelta, date
from sqlalchemy.sql import  case
from sqlalchemy.orm import aliased
from typing import Optional 
from loguru import logger
import pytz
from datetime import datetime, timedelta, date, time
from app.events import models as event_models # or wherever Event is
from app.users.permissions import role_required  # 👈 permission helper

from zoneinfo import ZoneInfo
from sqlalchemy import func
from typing import Optional




router = APIRouter()




@router.post("/", response_model=eventpayment_schemas.EventPaymentResponse)
def create_event_payment(
    payment_data: eventpayment_schemas.EventPaymentCreate,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    
    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve Business ID
    # --------------------------------------------------
    if "super_admin" in roles:
        if not business_id:
            raise HTTPException(status_code=400, detail="business_id is required for super admin")
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Fetch Event and Validate Ownership
    # --------------------------------------------------
    event = db.query(event_models.Event).filter(
        event_models.Event.id == payment_data.event_id,
        event_models.Event.business_id == resolved_business_id
    ).first()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if event.payment_status.lower() == "cancelled":
        raise HTTPException(
            status_code=400,
            detail=f"Payment cannot be processed because Event ID {payment_data.event_id} is cancelled."
        )

    # --------------------------------------------------
    # Calculate totals excluding voided payments
    # --------------------------------------------------
    total_paid = db.query(
        func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0)
    ).filter(
        eventpayment_models.EventPayment.event_id == payment_data.event_id,
        eventpayment_models.EventPayment.payment_status != "voided"
    ).scalar()

    total_discount = db.query(
        func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
    ).filter(
        eventpayment_models.EventPayment.event_id == payment_data.event_id,
        eventpayment_models.EventPayment.payment_status != "voided"
    ).scalar()

    new_total_paid = float(total_paid) + float(payment_data.amount_paid or 0)
    new_total_discount = float(total_discount) + float(payment_data.discount_allowed or 0)

    total_cost = float(event.event_amount or 0) + float(event.caution_fee or 0)

    balance_due = total_cost - (new_total_paid + new_total_discount)

    # --------------------------------------------------
    # Determine Payment Status
    # --------------------------------------------------
    if balance_due > 0:
        payment_status = "incomplete"
    elif balance_due == 0:
        payment_status = "complete"
    else:
        payment_status = "excess"

    # --------------------------------------------------
    # Create Payment with UTC timestamp
    # --------------------------------------------------
    new_payment = eventpayment_models.EventPayment(
        business_id=resolved_business_id,
        event_id=payment_data.event_id,
        organiser=payment_data.organiser,
        event_amount=event.event_amount,
        amount_paid=payment_data.amount_paid,
        discount_allowed=payment_data.discount_allowed,
        balance_due=balance_due,
        payment_method=payment_data.payment_method,
        bank=payment_data.bank,
        payment_status=payment_status,
        created_by=current_user.username,
        created_at=datetime.now(ZoneInfo("UTC"))
    )

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)

    return new_payment


@router.get("/outstanding")
def list_outstanding_events(
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve Business ID
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Fetch events (excluding cancelled)
    # --------------------------------------------------
    query = db.query(event_models.Event).filter(
        event_models.Event.payment_status != "cancelled"
    )

    if resolved_business_id:
        query = query.filter(event_models.Event.business_id == resolved_business_id)

    events = query.order_by(event_models.Event.start_datetime.desc()).all()

    outstanding = []

    for event in events:

        total_due = float(event.event_amount or 0) + float(event.caution_fee or 0)

        # --------------------------------------------------
        # Calculate totals excluding voided payments
        # --------------------------------------------------
        totals = db.query(
            func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
            func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
        ).filter(
            eventpayment_models.EventPayment.event_id == event.id,
            eventpayment_models.EventPayment.payment_status != "voided"
        ).first()

        total_paid = float(totals[0] or 0)
        total_discount = float(totals[1] or 0)

        balance_due = total_due - (total_paid + total_discount)

        if balance_due > 0:
            outstanding.append({
                "event_id": event.id,
                "organizer": event.organizer,
                "title": event.title,
                "location": event.location,
                "start_date": event.start_datetime,
                "end_date": event.end_datetime,
                "total_due": total_due,
                "total_paid": total_paid,
                "discount_allowed": total_discount,
                "amount_due": balance_due,
                "payment_status": "incomplete"
            })

    # --------------------------------------------------
    # Return summary
    # --------------------------------------------------
    if not outstanding:
        return {
            "total_outstanding": 0,
            "total_outstanding_balance": 0,
            "outstanding_events": []
        }

    total_outstanding_balance = sum(item["amount_due"] for item in outstanding)

    return {
        "total_outstanding": len(outstanding),
        "total_outstanding_balance": total_outstanding_balance,
        "outstanding_events": outstanding
    }




@router.get("/")
def list_event_payments(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):

    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Base query with event join
    # --------------------------------------------------
    query = (
        db.query(eventpayment_models.EventPayment, event_models.Event)
        .join(event_models.Event, event_models.Event.id == eventpayment_models.EventPayment.event_id)
    )

    if resolved_business_id:
        query = query.filter(event_models.Event.business_id == resolved_business_id)

    # --------------------------------------------------
    # Date filtering using ZoneInfo
    # --------------------------------------------------
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("UTC"))
            end_dt = (
                datetime.strptime(end_date, "%Y-%m-%d")
                + timedelta(days=1)
                - timedelta(seconds=1)
            ).replace(tzinfo=ZoneInfo("UTC"))

            query = query.filter(
                and_(
                    eventpayment_models.EventPayment.payment_date >= start_dt,
                    eventpayment_models.EventPayment.payment_date <= end_dt,
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    results = query.order_by(eventpayment_models.EventPayment.payment_date.desc()).all()

    formatted_payments = []

    total_event_cost = 0
    total_paid_amount = 0
    total_due_amount = 0
    unique_events = set()

    bank_summary: Dict[str, Dict[str, float]] = {}

    # --------------------------------------------------
    # Process payments
    # --------------------------------------------------
    for payment, event in results:

        event_amount = float(event.event_amount or 0)
        caution_fee = float(event.caution_fee or 0)
        total_due = event_amount + caution_fee

        # Calculate valid totals
        totals = db.query(
            func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
            func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
        ).filter(
            eventpayment_models.EventPayment.event_id == event.id,
            eventpayment_models.EventPayment.payment_status != "voided"
        ).first()

        total_valid_paid = float(totals[0])
        total_valid_discount = float(totals[1])

        balance_due = total_due - (total_valid_paid + total_valid_discount)

        # Determine payment status
        if payment.payment_status == "voided":
            status = "voided"
        elif balance_due > 0:
            status = "incomplete"
        elif balance_due == 0:
            status = "complete"
        else:
            status = "excess"

        formatted_payments.append({
            "id": payment.id,
            "event_id": payment.event_id,
            "organiser": payment.organiser,
            "event_amount": event_amount,
            "caution_fee": caution_fee,
            "total_due": total_due,
            "amount_paid": float(payment.amount_paid or 0),
            "discount_allowed": float(payment.discount_allowed or 0),
            "balance_due": balance_due,
            "payment_method": payment.payment_method,
            "bank": payment.bank,
            "payment_status": status,
            "payment_date": payment.payment_date.astimezone(ZoneInfo("UTC")).isoformat(),
            "created_by": payment.created_by,
        })

        # Totals (exclude voided)
        if payment.payment_status != "voided":

            if payment.event_id not in unique_events:
                unique_events.add(payment.event_id)
                total_event_cost += total_due
                total_due_amount += balance_due

            total_paid_amount += float(payment.amount_paid or 0)

            # Bank summary
            if payment.bank:
                bank = payment.bank.upper()

                if bank not in bank_summary:
                    bank_summary[bank] = {"pos": 0.0, "transfer": 0.0}

                method = (payment.payment_method or "").lower()

                if method in ("pos", "pos card", "card"):
                    bank_summary[bank]["pos"] += float(payment.amount_paid or 0)

                elif method == "bank transfer":
                    bank_summary[bank]["transfer"] += float(payment.amount_paid or 0)

    # --------------------------------------------------
    # Payment method summary
    # --------------------------------------------------
    summary_query = db.query(
        eventpayment_models.EventPayment.payment_method,
        func.sum(eventpayment_models.EventPayment.amount_paid)
    ).filter(eventpayment_models.EventPayment.payment_status != "voided")

    if start_date and end_date:
        summary_query = summary_query.filter(
            and_(
                eventpayment_models.EventPayment.payment_date >= start_dt,
                eventpayment_models.EventPayment.payment_date <= end_dt
            )
        )

    summary_results = summary_query.group_by(
        eventpayment_models.EventPayment.payment_method
    ).all()

    summary = {"total_cash": 0.0, "total_pos": 0.0, "total_transfer": 0.0}

    for method, total in summary_results:
        if not method:
            continue

        m = method.lower()

        if m == "cash":
            summary["total_cash"] = float(total)

        elif m in ("pos", "pos card", "card"):
            summary["total_pos"] = float(total)

        elif m == "bank transfer":
            summary["total_transfer"] = float(total)

    summary["total_payment"] = round(
        summary["total_cash"] +
        summary["total_pos"] +
        summary["total_transfer"], 2
    )

    return {
        "payments": formatted_payments,
        "summary": {
            "total_event_cost": total_event_cost,
            "total_paid": total_paid_amount,
            "total_due": total_due_amount,
            "by_method": summary,
            "by_bank": bank_summary
        }
    }



@router.get("/eventpayment/{payment_id}", response_model=dict)
def get_event_payment(
    payment_id: int,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):

    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Fetch payment + event together
    # --------------------------------------------------
    result = (
        db.query(eventpayment_models.EventPayment, event_models.Event)
        .join(event_models.Event, event_models.Event.id == eventpayment_models.EventPayment.event_id)
        .filter(eventpayment_models.EventPayment.id == payment_id)
    )

    if resolved_business_id:
        result = result.filter(event_models.Event.business_id == resolved_business_id)

    record = result.first()

    if not record:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment, event = record

    # --------------------------------------------------
    # Calculate totals excluding voided payments
    # --------------------------------------------------
    totals = db.query(
        func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
        func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
    ).filter(
        eventpayment_models.EventPayment.event_id == payment.event_id,
        eventpayment_models.EventPayment.payment_status != "voided"
    ).first()

    total_paid = float(totals[0])
    total_discount = float(totals[1])

    event_amount = float(event.event_amount or 0)
    caution_fee = float(event.caution_fee or 0)

    total_due = event_amount + caution_fee
    balance_due = total_due - (total_paid + total_discount)

    # --------------------------------------------------
    # Determine payment status
    # --------------------------------------------------
    if payment.payment_status == "voided":
        status = "voided"
    elif balance_due > 0:
        status = "incomplete"
    elif balance_due == 0:
        status = "complete"
    else:
        status = "excess"

    return {
        "id": payment.id,
        "event_id": payment.event_id,
        "organiser": payment.organiser,
        "event_amount": event_amount,
        "caution_fee": caution_fee,
        "total_due": total_due,
        "amount_paid": float(payment.amount_paid or 0),
        "discount_allowed": float(payment.discount_allowed or 0),
        "balance_due": balance_due,
        "payment_method": payment.payment_method,
        "bank": payment.bank,
        "payment_status": status,
        "payment_date": (
            payment.payment_date.astimezone(ZoneInfo("UTC")).isoformat()
            if payment.payment_date else None
        ),
        "created_by": payment.created_by,
    }


@router.get("/event_debtor_list")
def get_event_debtor_list(
    organiser_name: Optional[str] = Query(None, description="Filter by organiser name"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):

    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Validate dates
    # --------------------------------------------------
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be later than end date.")

    start_dt = (
        datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ZoneInfo("UTC"))
        if start_date else None
    )

    end_dt = (
        datetime.combine(end_date, datetime.max.time()).replace(tzinfo=ZoneInfo("UTC"))
        if end_date else None
    )

    # --------------------------------------------------
    # Base event query
    # --------------------------------------------------
    query = db.query(event_models.Event).filter(
        event_models.Event.payment_status != "cancelled"
    )

    if resolved_business_id:
        query = query.filter(event_models.Event.business_id == resolved_business_id)

    if organiser_name:
        query = query.filter(event_models.Event.organizer.ilike(f"%{organiser_name}%"))

    if start_dt:
        query = query.filter(event_models.Event.created_at >= start_dt)

    if end_dt:
        query = query.filter(event_models.Event.created_at <= end_dt)

    events = query.all()

    debtor_list = []
    total_current_debt = 0
    total_database_debt = 0

    # --------------------------------------------------
    # Process events
    # --------------------------------------------------
    for event in events:

        totals = db.query(
            func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
            func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0),
            func.max(eventpayment_models.EventPayment.payment_date)
        ).filter(
            eventpayment_models.EventPayment.event_id == event.id,
            eventpayment_models.EventPayment.payment_status != "voided"
        ).first()

        total_paid = float(totals[0] or 0)
        total_discount = float(totals[1] or 0)
        last_payment_date = totals[2]

        event_amount = float(event.event_amount or 0)
        caution_fee = float(event.caution_fee or 0)

        total_due = event_amount + caution_fee
        balance_due = total_due - (total_paid + total_discount)

        # Determine status
        if balance_due > 0:
            payment_status = "incomplete"
        elif balance_due == 0:
            payment_status = "complete"
        else:
            payment_status = "excess"

        # Current debtors only
        if balance_due > 0:

            debtor_list.append({
                "event_id": event.id,
                "organiser": event.organizer,
                "title": event.title,
                "start_datetime": event.start_datetime,
                "end_datetime": event.end_datetime,
                "event_amount": event_amount,
                "caution_fee": caution_fee,
                "location": event.location,
                "phone_number": event.phone_number,
                "address": event.address,
                "payment_status": payment_status,
                "balance_due": balance_due,
                "total_paid": total_paid,
                "created_by": event.created_by,
                "created_at": (
                    event.created_at.astimezone(ZoneInfo("UTC")).isoformat()
                    if event.created_at else None
                ),
                "last_payment_date": (
                    last_payment_date.astimezone(ZoneInfo("UTC")).isoformat()
                    if last_payment_date else None
                ),
            })

            total_current_debt += balance_due

        total_database_debt += max(balance_due, 0)

    if not debtor_list:
        raise HTTPException(status_code=404, detail="No debtors found for the given criteria.")

    # --------------------------------------------------
    # Sort by latest payment
    # --------------------------------------------------
    debtor_list.sort(
        key=lambda x: x["last_payment_date"] if x["last_payment_date"] else "",
        reverse=True
    )

    return {
        "total_debtors": len(debtor_list),
        "total_current_debt": total_current_debt,
        "total_gross_debt": total_database_debt,
        "debtors": debtor_list,
    }



@router.get("/status", response_model=List[eventpayment_schemas.EventPaymentResponse])
def list_event_payments_by_status(
    status: Optional[str] = Query(None, description="Payment status (pending, complete, incomplete, voided)"),
    start_date: Optional[date] = Query(None, description="Start date yyyy-mm-dd"),
    end_date: Optional[date] = Query(None, description="End date yyyy-mm-dd"),
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):

    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Base query with event join (for tenant isolation)
    # --------------------------------------------------
    query = (
        db.query(eventpayment_models.EventPayment)
        .join(event_models.Event, event_models.Event.id == eventpayment_models.EventPayment.event_id)
    )

    if resolved_business_id:
        query = query.filter(event_models.Event.business_id == resolved_business_id)

    # --------------------------------------------------
    # Status filtering
    # --------------------------------------------------
    if status:
        valid_statuses = {"pending", "complete", "incomplete", "voided"}

        status_lower = status.lower()

        if status_lower not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Choose from: {valid_statuses}"
            )

        query = query.filter(
            eventpayment_models.EventPayment.payment_status == status_lower
        )

    # --------------------------------------------------
    # Date filtering (UTC safe)
    # --------------------------------------------------
    if start_date:
        start_dt = datetime.combine(
            start_date,
            datetime.min.time()
        ).replace(tzinfo=ZoneInfo("UTC"))

        query = query.filter(
            eventpayment_models.EventPayment.payment_date >= start_dt
        )

    if end_date:
        end_dt = datetime.combine(
            end_date,
            datetime.max.time()
        ).replace(tzinfo=ZoneInfo("UTC"))

        query = query.filter(
            eventpayment_models.EventPayment.payment_date <= end_dt
        )

    payments = query.order_by(
        eventpayment_models.EventPayment.payment_date.desc()
    ).all()

    if not payments:
        return []

    return payments





from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import func

@router.put("/void/{payment_id}/", response_model=dict)
def void_event_payment(
    payment_id: int,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["admin"]))
):

    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    try:

        # --------------------------------------------------
        # Fetch payment with event
        # --------------------------------------------------
        query = (
            db.query(eventpayment_models.EventPayment, event_models.Event)
            .join(
                event_models.Event,
                event_models.Event.id == eventpayment_models.EventPayment.event_id
            )
            .filter(eventpayment_models.EventPayment.id == payment_id)
        )

        if resolved_business_id is not None:
            query = query.filter(event_models.Event.business_id == resolved_business_id)

        result = query.first()

        if not result:
            raise HTTPException(status_code=404, detail="Payment not found")

        payment, event = result

        # --------------------------------------------------
        # Prevent double void
        # --------------------------------------------------
        if payment.payment_status == "voided":
            raise HTTPException(status_code=400, detail="Payment already voided")

        # --------------------------------------------------
        # Void payment
        # --------------------------------------------------
        payment.payment_status = "voided"
        payment.updated_at = datetime.now(ZoneInfo("UTC"))

        # --------------------------------------------------
        # Recalculate event totals
        # --------------------------------------------------
        totals = db.query(
            func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
            func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
        ).filter(
            eventpayment_models.EventPayment.event_id == event.id,
            eventpayment_models.EventPayment.payment_status != "voided"
        ).first()

        total_paid = float(totals[0] or 0)
        total_discount = float(totals[1] or 0)

        event_total_due = float(event.event_amount or 0) + float(event.caution_fee or 0)

        event.balance_due = event_total_due - (total_paid + total_discount)

        # --------------------------------------------------
        # Update event payment status
        # --------------------------------------------------
        if event.balance_due > 0:
            event.payment_status = "pending"
        else:
            event.payment_status = "complete"

        event.updated_at = datetime.now(ZoneInfo("UTC"))

        db.commit()

        return {
            "message": f"Event payment {payment_id} successfully voided",
            "payment_details": {
                "payment_id": payment.id,
                "status": payment.payment_status
            },
            "event_details": {
                "event_id": event.id,
                "balance_due": event.balance_due,
                "payment_status": event.payment_status
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error voiding payment: {str(e)}"
        )



@router.get("/{payment_id}")
def get_event_payment_by_id(
    payment_id: int,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        resolved_business_id = business_id
        if not resolved_business_id:
            raise HTTPException(status_code=400, detail="business_id is required for super admin")
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Fetch payment and join event (tenant safe)
    # --------------------------------------------------
    record = (
        db.query(eventpayment_models.EventPayment, event_models.Event)
        .join(event_models.Event, event_models.Event.id == eventpayment_models.EventPayment.event_id)
        .filter(eventpayment_models.EventPayment.id == payment_id)
        .filter(event_models.Event.business_id == resolved_business_id)
    )

    result = record.first()
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment, event = result

    # --------------------------------------------------
    # Compute totals excluding voided payments
    # --------------------------------------------------
    total_paid, total_discount = db.query(
        func.coalesce(func.sum(eventpayment_models.EventPayment.amount_paid), 0),
        func.coalesce(func.sum(eventpayment_models.EventPayment.discount_allowed), 0)
    ).filter(
        eventpayment_models.EventPayment.event_id == event.id,
        eventpayment_models.EventPayment.payment_status != "voided"
    ).first()

    event_amount = float(event.event_amount or 0)
    caution_fee = float(event.caution_fee or 0)
    total_due = event_amount + caution_fee
    balance_due = total_due - (float(total_paid or 0) + float(total_discount or 0))

    # --------------------------------------------------
    # Format response with timezone-aware datetimes
    # --------------------------------------------------
    formatted_payment = {
        "id": payment.id,
        "event_id": payment.event_id,
        "organiser": payment.organiser,
        "event_amount": event_amount,
        "caution_fee": caution_fee,
        "total_due": total_due,
        "amount_paid": float(payment.amount_paid or 0),
        "discount_allowed": float(payment.discount_allowed or 0),
        "balance_due": balance_due,
        "payment_method": payment.payment_method,
        "payment_status": payment.payment_status,
        "payment_date": payment.payment_date.replace(tzinfo=ZoneInfo("UTC")) if payment.payment_date else None,
        "created_by": payment.created_by,
    }

    return formatted_payment

