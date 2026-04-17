from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from sqlalchemy import and_
from sqlalchemy import func
from app.events import models as event_models
from app.events import schemas as event_schemas
from app.users import schemas as user_schemas
from app.users.auth import get_current_user
from app.users.permissions import role_required  # 👈 permission helper
from datetime import datetime, time
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from datetime import datetime
from zoneinfo import ZoneInfo




router = APIRouter()





from datetime import datetime, date, time
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

@router.post("/", response_model=event_schemas.EventResponse)
def create_event(
    event: event_schemas.EventCreate,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    roles = set(current_user.roles)

    # --------------------------------------------------
    # Resolve business_id
    # --------------------------------------------------
    if "super_admin" in roles:
        if not business_id:
            raise HTTPException(status_code=400, detail="business_id is required for super admin")
        resolved_business_id = business_id
    else:
        resolved_business_id = current_user.business_id

    # --------------------------------------------------
    # Normalize start and end datetime
    # --------------------------------------------------
    try:
        # Helper function to convert date/datetime to UTC datetime
        def to_utc_datetime(dt):
            if isinstance(dt, date) and not isinstance(dt, datetime):
                return datetime.combine(dt, time.min).replace(tzinfo=ZoneInfo("UTC"))
            elif isinstance(dt, datetime):
                # If naive datetime, attach UTC
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=ZoneInfo("UTC"))
                return dt.astimezone(ZoneInfo("UTC"))
            else:
                raise ValueError("Invalid datetime format.")

        start_dt = to_utc_datetime(event.start_datetime)
        end_dt = to_utc_datetime(event.end_datetime)
        # Ensure end >= start
        if end_dt < start_dt:
            raise ValueError("end_datetime cannot be before start_datetime.")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {str(e)}")

    # --------------------------------------------------
    # Prevent duplicate event (same start date + location + business)
    # --------------------------------------------------
    existing_event = db.query(event_models.Event).filter(
        event_models.Event.business_id == resolved_business_id,
        event_models.Event.start_datetime == start_dt,
        func.lower(event_models.Event.location) == event.location.lower()
    ).first()

    if existing_event:
        raise HTTPException(
            status_code=400,
            detail=f"An event has already been booked on {start_dt.date()} at {event.location}. "
                   f"Please choose a different date or location."
        )

    # --------------------------------------------------
    # Create Event
    # --------------------------------------------------
    db_event = event_models.Event(
        business_id=resolved_business_id,
        organizer=event.organizer,
        title=event.title,
        description=event.description,
        start_datetime=start_dt,
        end_datetime=end_dt,
        event_amount=event.event_amount,
        caution_fee=event.caution_fee,
        location=event.location,
        phone_number=event.phone_number,
        address=event.address,
        payment_status=event.payment_status or "active",
        created_by=current_user.username
    )

    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    return db_event



from fastapi.responses import JSONResponse

@router.get("/")
def list_events(
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD format"),
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

    query = db.query(event_models.Event).options(joinedload(event_models.Event.payments))

    # Filter by business
    if resolved_business_id:
        query = query.filter(event_models.Event.business_id == resolved_business_id)

    # --------------------------------------------------
    # Filter by start_date / end_date
    # --------------------------------------------------
    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
            # Normalize to UTC
            start_dt = start_dt.replace(tzinfo=ZoneInfo("UTC"))
            end_dt = end_dt.replace(tzinfo=ZoneInfo("UTC"))

            query = query.filter(
                and_(
                    event_models.Event.start_datetime >= start_dt,
                    event_models.Event.end_datetime <= end_dt
                )
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    events = query.order_by(event_models.Event.start_datetime).all()

    # --------------------------------------------------
    # Recompute payment status & balance
    # --------------------------------------------------
    for event in events:
        if event.payment_status == "cancelled":
            continue

        total_due = float(event.event_amount or 0) + float(event.caution_fee or 0)
        total_paid = sum(
            float(p.amount_paid or 0)
            for p in event.payments
            if p.payment_status != "voided"
        )
        total_discount = sum(
            float(p.discount_allowed or 0)
            for p in event.payments
            if p.payment_status != "voided"
        )
        balance_due = total_due - (total_paid + total_discount)

        # Update payment_status dynamically
        if balance_due > 0:
            event.payment_status = "incomplete"
        elif balance_due == 0:
            event.payment_status = "complete"
        else:
            event.payment_status = "excess"

    # --------------------------------------------------
    # Compute summary
    # --------------------------------------------------
    filtered_events = [e for e in events if e.payment_status != "cancelled"]
    total_amount = sum(e.event_amount or 0 for e in filtered_events)

    summary = {
        "total_entries": len(events),
        "total_booking_amount": total_amount
    }

    return JSONResponse(content={
        "events": jsonable_encoder(events),
        "summary": summary
    })



# --------------------------------------------------
# GET Event by ID
# --------------------------------------------------
@router.get("/{event_id}", response_model=event_schemas.EventResponse)
def get_event(
    event_id: int,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    # Resolve business
    roles = set(current_user.roles)
    resolved_business_id = business_id if "super_admin" in roles else current_user.business_id

    # Fetch event
    db_event = db.query(event_models.Event).filter(event_models.Event.id == event_id).first()
    if not db_event or (resolved_business_id and db_event.business_id != resolved_business_id):
        raise HTTPException(status_code=404, detail="Event not found")
    
    return db_event


# --------------------------------------------------
# Update Event (Only Creator or Admin)
# --------------------------------------------------
@router.put("/{event_id}", response_model=dict)
def update_event(
    event_id: int,
    event: event_schemas.EventCreate,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    roles = set(current_user.roles)
    resolved_business_id = business_id if "super_admin" in roles else current_user.business_id

    db_event = db.query(event_models.Event).filter(event_models.Event.id == event_id).first()
    if not db_event or (resolved_business_id and db_event.business_id != resolved_business_id):
        raise HTTPException(status_code=404, detail="Event not found")

    if db_event.payment_status.lower() == "cancelled":
        raise HTTPException(status_code=400, detail="Cancelled events cannot be updated")

    if db_event.created_by != current_user.username and "admin" not in roles:
        raise HTTPException(status_code=403, detail="Only event creators or admins can update events")

    # --------------------------------------------------
    # Normalize date/datetime fields
    # --------------------------------------------------
    def to_utc_datetime(dt):
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return datetime.combine(dt, time.min).replace(tzinfo=ZoneInfo("UTC"))
        elif isinstance(dt, datetime):
            if dt.tzinfo is None:
                return dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("UTC"))
        return dt

    update_data = event.dict(exclude_unset=True)
    if "start_datetime" in update_data:
        update_data["start_datetime"] = to_utc_datetime(update_data["start_datetime"])
    if "end_datetime" in update_data:
        update_data["end_datetime"] = to_utc_datetime(update_data["end_datetime"])

    for field, value in update_data.items():
        setattr(db_event, field, value)

    db.commit()
    db.refresh(db_event)

    return {"message": "Event updated successfully"}


# --------------------------------------------------
# Cancel Event
# --------------------------------------------------
@router.put("/{event_id}/cancel", response_model=dict)
def cancel_event(
    event_id: int, 
    cancellation_reason: str,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db), 
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["event"]))
):
    roles = set(current_user.roles)
    resolved_business_id = business_id if "super_admin" in roles else current_user.business_id

    db_event = db.query(event_models.Event).filter(event_models.Event.id == event_id).first()
    if not db_event or (resolved_business_id and db_event.business_id != resolved_business_id):
        raise HTTPException(status_code=404, detail="Event not found")

    if db_event.payment_status.lower() == "cancelled":
        raise HTTPException(status_code=400, detail="Event is already cancelled")

    db_event.payment_status = "cancelled"
    db_event.cancellation_reason = cancellation_reason

    try:
        db.commit()
        db.refresh(db_event)

        return {
            "message": "Event cancellation successful",
            "cancellation_reason": db_event.cancellation_reason,
            "payment_status": db_event.payment_status
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")