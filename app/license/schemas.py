# app/license/schemas.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class LicenseCreate(BaseModel):
    key: str = Field(..., min_length=6, description="License key string")
    expiration_date: datetime = Field(..., description="Expiration date/time")
    business_id: int = Field(..., description="Business this license belongs to")


class LicenseResponse(BaseModel):
    id: int
    key: str
    is_active: bool
    created_at: datetime
    expiration_date: datetime
    business_id: int

    class Config:
        from_attributes = True


class LicenseStatusResponse(BaseModel):
    valid: bool
    expires_on: Optional[datetime] = None
    message: Optional[str] = None
    warning: Optional[bool] = False
    days_left: Optional[int] = None
