from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.vendor.schemas import VendorDisplay  # ✅ import this
from app.vendor.schemas import VendorInStoreDisplay  # make sure this import path is correct
from app.vendor.schemas import VendorOut
#from app.bar.schemas import BarDisplaySimple
from pydantic import BaseModel, Field
from typing import Optional, List, Literal, Union
from app.bar.schemas import BarDisplaySimple
from app.kitchen.schemas import KitchenDisplaySimple




class SomeSchema(BaseModel):
    related: 'BarDisplaySimple'  # use a string to avoid import issues


# ----------------------------
# Store Category
# ----------------------------
class StoreCategoryBase(BaseModel):
    name: str


class StoreCategoryCreate(StoreCategoryBase):
    pass


class StoreCategoryDisplay(StoreCategoryBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ----------------------------
# Store Item
# ----------------------------
class StoreItemBase(BaseModel):
    name: str
    unit: str
    unit_price: float
    selling_price: float        # ✅ new
    category_id: Optional[int] = None
    item_type: Optional[str] = None




class StoreItemCreate(StoreItemBase):
    pass


# ✅ Nested item info
class StoreItemOut(BaseModel):
    id: int
    name: str
    unit: str
    unit_price: float
    selling_price: float        # ✅ new
    category_id: Optional[int] = None
    item_type: Optional[str] = None


    class Config:
        from_attributes = True



class StoreItemDisplay(BaseModel):
    id: int
    name: str
    unit: str
    category: Optional[StoreCategoryDisplay]
    item_type: Optional[str] = None
    unit_price: float
    selling_price: float        # ✅ new
    created_at: datetime
    


    class Config:
        from_attributes = True



#class StoreItemDisplay(BaseModel):
    #id: int
    #name: str
    #unit: str
    #unit_price: float
    #category_name: Optional[str]
    #created_at: datetime

    #class Config:
        #from_attributes = True



# ----------------------------
# Store Stock Entry (Purchase)
# ----------------------------
from fastapi import Form
from pydantic import BaseModel
from datetime import datetime

class StoreStockEntryCreate(BaseModel):
    item_id: int
    item_name: str
    invoice_number: str
    quantity: int
    unit_price: float
    vendor_id: int
    purchase_date: datetime
    


    @classmethod
    def as_form(
        cls,
        item_id: int = Form(...),
        item_name: str = Form(...),
        invoice_number: str = Form(...),
        quantity: int = Form(...),
        unit_price: float = Form(...),
        vendor_id: int = Form(...),
        purchase_date: datetime = Form(...),
        
    ):
        return cls(
            item_id=item_id,
            item_name=item_name,
            invoice_number=invoice_number,
            quantity=quantity,
            unit_price=unit_price,
            vendor_id=vendor_id,
            purchase_date=purchase_date,
            
        )




class PurchaseCreateList(BaseModel):
    id: int
    item_name: str
    invoice_number:str
    quantity: int
    unit_price: float
    total_amount: float
    purchase_date: datetime
    created_by: Optional[str]
    attachment_url: Optional[str]

    # ✅ Nested item and vendor
    item: Optional["StoreItemOut"] = None
    vendor: Optional["VendorOut"] = None

    class Config:
        from_attributes = True


# --- Display model for frontend lists ---
class StoreStockEntryDisplay(BaseModel):
    id: int
    item_name: str
    quantity: int
    unit_price: float
    total_amount: float
    purchase_date: datetime
    created_by: Optional[str]
    created_at: datetime
    attachment_url: Optional[str]
    kitchen_id: Optional[int] = None  # 👈 NEW

    # ✅ Show full vendor and item info
    item: Optional["StoreItemOut"]
    vendor: Optional["VendorOut"]

    class Config:
        from_attributes = True

class UpdatePurchase(BaseModel):
    id: int
    item_name: str
    quantity: int
    unit_price: float
    total_amount: float
    vendor_id: int
    purchase_date: datetime 
    created_at: datetime
    created_by: Optional[str]
    attachment: Optional[str]  # ✅ include this
    attachment_url: Optional[str]  # ✅ For frontend use

    class Config:
        from_attributes = True



# ----------------------------
# Store Issue
# ----------------------------
class IssueItemCreate(BaseModel):  # ✅ renamed from StoreIssueItemBase
    item_id: int
    quantity: int


class IssueCreate(BaseModel):  # ✅ renamed from StoreIssueCreate
    issue_to: Literal["bar", "kitchen"]
    issued_to_id: int        # ID of the bar/kitchen
    issue_items: List[IssueItemCreate]  # ✅ renamed from 'items'
    issue_date: datetime = Field(default_factory=datetime.utcnow)



class IssueItemDisplay(BaseModel):
    id: int
    item: StoreItemDisplay
    quantity: int

    class Config:
        from_attributes = True



class IssueDisplay(BaseModel):
    id: int
    issue_to: str  # "bar" or "kitchen"
    issued_to_id: int
    # Use a Union so it can be Bar or Kitchen display
    issued_to: Optional[Union['BarDisplaySimple', 'KitchenDisplaySimple']] = None
    issue_date: datetime
    issue_items: List[IssueItemDisplay]

    class Config:
        from_attributes = True

class IssueDisplayOut(BaseModel):  # ✅ renamed from StoreIssueDisplay
    id: int
    issue_to: str
    issued_to_id: int
    issue_date: datetime
    issue_items: List[IssueItemDisplay]

    class Config:
        from_attributes = True



class StoreInventoryAdjustmentCreate(BaseModel):
    item_id: int
    quantity_adjusted: int
    reason: str


class StoreInventoryAdjustmentDisplay(BaseModel):
    id: int
    item: StoreItemDisplay
    quantity_adjusted: int
    reason: str
    adjusted_by: str
    adjusted_at: datetime

    class Config:
        from_attributes = True


from app.bar.schemas import BarDisplaySimple
SomeSchema.update_forward_refs()


class BarStockBalanceRow(BaseModel):
    bar_id: int
    bar_name: str
    item_id: int
    item_name: str
    unit: Optional[str]        # ✅ Ensure this exists
    category_name: Optional[str]  # ✅ Ensure this exists
    item_type: Optional[str]   # <--- ADD THIS
    unit: Optional[str] = None
    quantity: float
    selling_price: float
    amount: float  # quantity * selling_price

class BarStockBalanceResponse(BaseModel):
    rows: List[BarStockBalanceRow]
    total_entries: int
    total_amount: float


class StoreStockBalance(BaseModel):
    item_id: int
    item_name: str
    category_name: Optional[str] = None
    item_type: Optional[str] = None   # NEW FIELD
    unit: Optional[str] = None
    opening_stock: float = 0

    total_received: float
    total_issued: float
    total_adjusted: float
    balance: float
    current_unit_price: float
    balance_total_amount: float

    class Config:
        from_attributes = True


class KitchenItemSimple(BaseModel):
    item_id: int
    item_name: str
    selling_price: float

    class Config:
        from_attributes = True

