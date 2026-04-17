# app/vendors/schemas.py

from pydantic import BaseModel
from typing import Optional
from datetime import datetime



class VendorBase(BaseModel):
    business_name: str
    address: str
    phone_number: str

class VendorCreate(VendorBase):
    pass



class VendorOut(BaseModel):
    id: int
    business_name: str
    address: str
    phone_number: str


    class Config:
        from_attributes = True


class VendorDisplay(BaseModel):
    id: int
    name: str
    phone: str
    address: str
    created_at: datetime

    class Config:
        from_attributes = True


class VendorInStoreDisplay(BaseModel):
    id: int
    name: str
    phone: str
    created_at: datetime

    class Config:
        from_attributes = True