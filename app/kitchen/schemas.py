from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from pydantic.config import ConfigDict  # this is the correct import in v2

# ------------------------------
# GENERIC ITEM SCHEMA FOR KITCHEN (Minimal for Issue Response)
# ------------------------------
class KitchenItemMinimalDisplay(BaseModel):
    id: int
    name: Optional[str] = None  # optional, can be None if name not available

    model_config = ConfigDict(from_attributes=True)


# ------------------------------
# BASIC KITCHEN DISPLAY
# ------------------------------
class KitchenBase(BaseModel):
    name: str

class KitchenCreate(KitchenBase):
    pass

class KitchenDisplaySimple(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# ------------------------------
# KITCHEN ISSUE ITEMS
# ------------------------------
class KitchenIssueItemDisplay(BaseModel):
    id: int
    item: KitchenItemMinimalDisplay
    quantity: float

    model_config = ConfigDict(from_attributes=True)

# ------------------------------
# KITCHEN INVENTORY VIEW
# ------------------------------
class KitchenInventoryDisplay(BaseModel):
    id: int
    kitchen: KitchenDisplaySimple
    item: KitchenItemMinimalDisplay
    quantity: float
    last_updated: datetime

    model_config = ConfigDict(from_attributes=True)

# ------------------------------
# KITCHEN STOCK REPORT
# ------------------------------
class KitchenStockDisplay(BaseModel):
    id: int
    kitchen: KitchenDisplaySimple
    item: KitchenItemMinimalDisplay
    total_issued: float
    total_used: float

    model_config = ConfigDict(from_attributes=True)


# ------------------------------
# STORE ISSUE → KITCHEN
# ------------------------------
class IssueToKitchenItem(BaseModel):
    item_id: int
    quantity: float

class IssueToKitchenCreate(BaseModel):
    kitchen_id: int
    issue_items: List[IssueToKitchenItem]
    issue_date: datetime = datetime.utcnow()

class IssueToKitchenItemDisplay(BaseModel):
    item: KitchenItemMinimalDisplay
    quantity: float

    model_config = ConfigDict(from_attributes=True)


class IssueToKitchenDisplay(BaseModel):
    id: int
    kitchen: KitchenDisplaySimple
    issue_items: List[IssueToKitchenItemDisplay]
    issue_date: datetime = Field(default_factory=datetime.utcnow)


    model_config = ConfigDict(from_attributes=True)


class KitchenStockBalance(BaseModel):
    kitchen_id: int
    kitchen_name: str
    item_id: int
    item_name: str
    category_name: Optional[str] = None
    item_type: Optional[str] = None
    unit: Optional[str] = None

    total_issued: float = 0        # what store issued to kitchen
    total_used: float = 0          # what restaurant sold (store_qty_used)
    total_adjusted: float = 0      # adjustments made via KitchenInventoryAdjustment
    balance: float = 0             # issued - used - adjusted
    last_unit_price: Optional[float] = None
    balance_total_amount: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
    # ------------------------------
# KITCHEN INVENTORY ADJUSTMENTS
# ------------------------------
class KitchenInventoryAdjustmentCreate(BaseModel):
    kitchen_id: int
    item_id: int
    quantity_adjusted: float
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KitchenInventoryAdjustmentDisplay(BaseModel):
    id: int
    kitchen_id: int
    item: KitchenItemMinimalDisplay
    quantity_adjusted: float
    reason: Optional[str] = None
    adjusted_by: str
    adjusted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KitchenInventorySimple(BaseModel):
    id: int
    name: str
    unit: Optional[str]
    quantity: float

    model_config = ConfigDict(from_attributes=True)


# kitchen_schemas.py

class KitchenInventoryAdjustmentUpdate(BaseModel):
    quantity_adjusted: float
    reason: Optional[str] = None





class KitchenMenuCreate(BaseModel):
    item_id: int
    selling_price: float
    

class KitchenMenuDisplay(BaseModel):
    id: int
    item_id: int
    item_name: Optional[str]
    selling_price: float

    model_config = ConfigDict(from_attributes=True)


class KitchenMenuUpdate(BaseModel):
    selling_price: float

    model_config = ConfigDict(from_attributes=True)


