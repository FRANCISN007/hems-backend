from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import Base
from app.core.mixins import BusinessMixin


# ----------------------------
# Bar
# ----------------------------
class Bar(Base, BusinessMixin):
    __tablename__ = "bars"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    location = Column(String, nullable=True)

    

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_bar_business_name"),
    )

    
    inventory_items = relationship(
        "BarInventory",
        back_populates="bar",
        cascade="all, delete-orphan"
    )

    sales = relationship(
        "BarSale",
        back_populates="bar",
        cascade="all, delete-orphan"
    )

    issues = relationship("StoreIssue", back_populates="bar")


# ----------------------------
# Bar Inventory
# ----------------------------
class BarInventory(Base, BusinessMixin):
    __tablename__ = "bar_inventory"

    id = Column(Integer, primary_key=True, index=True)

    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=False)

    

    bar_name = Column(String, nullable=True)

    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    item_name = Column(String)

    quantity = Column(Integer, default=0, nullable=False)

    selling_price = Column(Float, default=0)

    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    note = Column(String, nullable=True)

    bar = relationship("Bar", back_populates="inventory_items")
    item = relationship("StoreItem")
    

    sale_items = relationship(
        "BarSaleItem",
        back_populates="bar_inventory",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("business_id", "bar_id", "item_id", name="unique_bar_item"),
    )


# ----------------------------
# Bar Inventory Adjustment
# ----------------------------
class BarInventoryAdjustment(Base, BusinessMixin):
    __tablename__ = "bar_inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)

    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=False)

    

    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)

    quantity_adjusted = Column(Integer, nullable=False)

    reason = Column(String, nullable=True)

    adjusted_by = Column(String, nullable=True)

    adjusted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    bar = relationship("Bar")
    item = relationship("StoreItem")
    

# ----------------------------
# Bar Inventory Receipt
# ----------------------------
class BarInventoryReceipt(Base, BusinessMixin):
    __tablename__ = "bar_inventory_receipts"

    id = Column(Integer, primary_key=True, index=True)

    bar_id = Column(Integer, ForeignKey("bars.id"))

    
    bar_name = Column(String)

    item_id = Column(Integer, ForeignKey("store_items.id"))
    item_name = Column(String)

    quantity = Column(Integer)

    selling_price = Column(Float)

    received_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    note = Column(String)

    created_by = Column(String)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    


# ----------------------------
# Bar Sale
# ----------------------------
class BarSale(Base, BusinessMixin):
    __tablename__ = "bar_sales"

    id = Column(Integer, primary_key=True, index=True)

    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=False)

    

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # User entered date
    sale_date = Column(DateTime(timezone=True), nullable=False)

    # System timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    total_amount = Column(Float, default=0.0)

    status = Column(String, default="unpaid")

    bar = relationship("Bar", back_populates="sales")

    created_by_user = relationship("User", lazy="joined")

    

    payments = relationship(
        "BarPayment",
        back_populates="bar_sale",
        cascade="all, delete-orphan"
    )

    sale_items = relationship(
        "BarSaleItem",
        back_populates="sale",
        cascade="all, delete-orphan"
    )




    @property
    def created_by(self):
        return self.created_by_user.username if self.created_by_user else None


# ----------------------------
# Bar Sale Item
# ----------------------------
class BarSaleItem(Base, BusinessMixin):
    __tablename__ = "bar_sale_items"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(Integer, ForeignKey("bar_sales.id"), nullable=False)

    

    bar_inventory_id = Column(Integer, ForeignKey("bar_inventory.id"), nullable=False)

    quantity = Column(Integer, nullable=False)

    selling_price = Column(Float, nullable=False)

    total_amount = Column(Float, nullable=False)

    sale = relationship("BarSale", back_populates="sale_items")

    bar_inventory = relationship("BarInventory", back_populates="sale_items")

    
