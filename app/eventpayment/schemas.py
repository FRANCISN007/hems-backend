from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime

# Base Schema for EventPayment
class EventPaymentBase(BaseModel):
    event_id: int
    organiser: str
    amount_paid: float
    discount_allowed: float = 0.0
    payment_method: str
    bank: Optional[str] = None   # 👈 Added
    payment_status: Optional[str] = "pending"
    created_by: str

    class Config:
        from_attributes = True

class EventPaymentCreate(EventPaymentBase):
    note: Optional[str] = None   # Optional note field

class EventPaymentResponse(BaseModel):
    id: int
    event_id: int
    organiser: str
    event_amount: float
    amount_paid: float
    discount_allowed: float
    balance_due: float
    payment_method: str
    bank: Optional[str] = None   # 👈 Added
    payment_status: str
    payment_date: datetime
    created_by: str
    note: Optional[str] = None

    class Config:
        from_attributes = True