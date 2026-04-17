from app.database import Base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import os
from app.bar.models import Bar
from app.kitchen.models import Kitchen
from app.core.mixins import BusinessMixin

from zoneinfo import ZoneInfo
from datetime import datetime

WAT = ZoneInfo("Africa/Lagos")

def get_local_time():
    return datetime.now(WAT)



# ----------------------------
# 1. Store Category
# ----------------------------
class StoreCategory(Base, BusinessMixin):
    __tablename__ = "store_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    

    created_at = Column(DateTime(timezone=True), default=get_local_time)

    items = relationship("StoreItem", back_populates="category")


# ----------------------------
# 2. Store Item
# ----------------------------
WAT = ZoneInfo("Africa/Lagos")

class StoreItem(Base, BusinessMixin):
    __tablename__ = "store_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False)
    category_id = Column(Integer, ForeignKey("store_categories.id"), nullable=True)
    unit_price = Column(Float, default=0.0, nullable=False)
    selling_price = Column(Float, default=0.0, nullable=False)
    item_type = Column(String(20), nullable=True)

    # Relationship
    category = relationship("StoreCategory")

    # ✅ Timezone-aware created_at like Booking
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(WAT)
    )

    # Relationships
    stock_entries = relationship("StoreStockEntry", back_populates="item")
    issue_items = relationship("StoreIssueItem", back_populates="item")
    meal_order_items = relationship("MealOrderItem", back_populates="store_item")


# ----------------------------
# 3. Store Stock Entry (Purchase)
# ----------------------------
class StoreStockEntry(Base, BusinessMixin):
    __tablename__ = "store_stock_entries"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    item_name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    original_quantity = Column(Integer, nullable=False)
    invoice_number = Column(String(255), nullable=True)
    unit_price = Column(Float, nullable=True)
    total_amount = Column(Float)
    vendor_id = Column(Integer, ForeignKey("vendors.id"))
    
    # ✅ Timezone-aware timestamps
    purchase_date = Column(DateTime(timezone=True), default=lambda: datetime.now(WAT), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(WAT), nullable=False)
    
    created_by = Column(String, nullable=False)
    attachment = Column(String, nullable=True)

    # Relationships
    item = relationship("StoreItem")
    vendor = relationship("Vendor", back_populates="purchases")

    @property
    def attachment_url(self):
        if self.attachment:
            return f"/attachments/store_invoices/{os.path.basename(self.attachment)}"
        return None


# ----------------------------
# 4. Store Issue
# ----------------------------
class StoreIssue(Base, BusinessMixin):
    __tablename__ = "store_issues"

    id = Column(Integer, primary_key=True, index=True)
    issue_to = Column(String, nullable=False)
    issued_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=True)
    kitchen_id = Column(Integer, ForeignKey("kitchens.id"), nullable=True)
    
    # ✅ Timezone-aware issue_date
    issue_date = Column(DateTime(timezone=True), default=lambda: datetime.now(WAT), nullable=False)

    # Relationships
    issue_items = relationship(
        "StoreIssueItem",
        back_populates="issue",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    bar = relationship("Bar", back_populates="issues")
    kitchen = relationship("Kitchen", back_populates="issues")



    

class StoreIssueItem(Base, BusinessMixin):
    __tablename__ = "store_issue_items"

    id = Column(Integer, primary_key=True, index=True)
    issue_id = Column(Integer, ForeignKey("store_issues.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False)

    

    issue = relationship("StoreIssue", back_populates="issue_items")
    item = relationship("StoreItem", back_populates="issue_items")


# ----------------------------
# 5. Store Inventory Adjustment
# ----------------------------
class StoreInventoryAdjustment(Base, BusinessMixin):
    __tablename__ = "store_inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    quantity_adjusted = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    adjusted_by = Column(String, nullable=False)
    adjusted_at = Column(DateTime(timezone=True), default=get_local_time)

   

    item = relationship("StoreItem")


# ----------------------------
# 6. Store Inventory
# ----------------------------
class StoreInventory(Base, BusinessMixin):
    __tablename__ = "store_inventory"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), unique=True, nullable=False)
    quantity = Column(Integer, default=0)

    # ✅ Timezone-aware last_updated like Booking
    last_updated = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(WAT),
        onupdate=lambda: datetime.now(WAT),
        nullable=False
    )

    # Relationship
    item = relationship("StoreItem")