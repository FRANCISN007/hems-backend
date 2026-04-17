# app/barpayment/schemas.py

from pydantic import BaseModel
from typing import Optional, Literal
from typing import Optional
from datetime import date, datetime


# schemas.py

class BarPaymentCreate(BaseModel):
    bar_sale_id: int
    amount_paid: float
    payment_method: Literal["cash", "transfer", "pos"]
    bank: Optional[str] = None  # 👈 NEW
    note: Optional[str] = None
    date_paid: Optional[date] = None  # ✅ match model


class BarPaymentDisplay(BaseModel):
    id: int
    bar_sale_id: int
    sale_amount: float
    amount_paid: float
    balance_due: float
    payment_method: Literal["cash", "transfer", "pos"]
    bank: Optional[str] = None  # 👈 NEW
    date_paid: datetime
    status: str
    created_by: str
    note: Optional[str] = None

    class Config:
        from_attributes = True
        



class BarPaymentUpdate(BaseModel):
    amount_paid: Optional[float] = None
    payment_method: Optional[Literal["cash", "transfer", "pos"]] = None
    bank: Optional[str] = None  # 👈 NEW
    note: Optional[str] = None



class BarPaymentVoid(BaseModel):
    void: bool  # If True, will void


class BarPaymentOutstanding(BaseModel):
    id: int
    bar_sale_id: int
    amount_paid: float
    payment_method: Literal["cash", "transfer", "pos"]
    bank: Optional[str] = None  # 👈 NEW
    note: Optional[str] = None
    date_paid: datetime
    status: str
    total_sale: float
    balance_due: float

    class Config:
        from_attributes = True


class BarOutstandingDisplay(BaseModel):
    bar_sale_id: int
    sale_amount: float
    amount_paid: float
    balance_due: float
    status: str

    class Config:
        from_attributes = True


class BarOutstandingSummary(BaseModel):
    total_entries: int
    total_due: float
    results: list[BarOutstandingDisplay]
