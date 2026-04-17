from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

from app.core.timezone import now_wat, to_wat


class PaymentCreateSchema(BaseModel):
    amount_paid: float
    discount_allowed: Optional[float] = 0.0
    payment_method: str

    payment_date: Optional[datetime] = None  # ✅ FIXED

    created_by: Optional[str] = None
    bank_id: Optional[int] = None

    class Config:
        from_attributes = True

    def model_post_init(self, __context):
        if self.payment_date:
            self.payment_date = to_wat(self.payment_date)



class PaymentUpdateSchema(BaseModel):
    guest_name: Optional[str] = None
    room_number: Optional[str] = None

    amount_paid: Optional[float] = None
    discount_allowed: Optional[float] = None
    payment_method: Optional[str] = None

    # ✅ WAT default
    payment_date: Optional[datetime] = Field(default_factory=now_wat)

    status: Optional[str] = None

    class Config:
        from_attributes = True

    # ✅ Normalize timezone
    def model_post_init(self, __context):
        if self.payment_date:
            self.payment_date = to_wat(self.payment_date)
