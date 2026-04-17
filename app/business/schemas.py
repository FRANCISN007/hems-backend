# app/business/schemas.py (fully rewritten - removed static is_active, use dynamic in response)
from pydantic import BaseModel
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class BusinessBase(BaseModel):
    name: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]


class BusinessCreate(BusinessBase):
    owner_username: str = Field(..., min_length=3, description="Username of the business owner/admin")


class BusinessUpdate(BaseModel):
    name: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]


# app/business/schemas.py
class BusinessOut(BusinessBase):
    id: int
    license_active: Optional[bool] = None  # ← allow None, we set it manually
    expiration_date: Optional[datetime] = None   # ← ADD THIS LINE
    created_at: datetime
    owner_username: Optional[str] = None  # ← NEW: username of the business owner/admin

    class Config:
        from_attributes = True


class BusinessListResponse(BaseModel):
    total: int
    businesses: List[BusinessOut]




class BusinessSimple(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
