# event_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from typing import Union


class EventBase(BaseModel):
    organizer: str
    title: str
    description: Optional[str] = None
    start_datetime: Union[date, datetime]
    end_datetime: Union[date, datetime]
    event_amount: float
    caution_fee: float
    location: Optional[str] = None
    phone_number: str
    address: str
    payment_status: Optional[str] = "active"
    balance_due: float
    created_by: Optional[str] = None
    cancellation_reason: Optional[str] = None

    class Config:
        from_attributes = True


class EventCreate(EventBase):
    pass


class EventResponse(EventBase):
    id: int
    created_at: datetime
    updated_at: datetime
