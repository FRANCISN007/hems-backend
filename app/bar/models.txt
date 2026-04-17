from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
from sqlalchemy import DateTime, func


# ----------------------------
# Bar
# ----------------------------
class Bar(Base):
    __tablename__ = "bars"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    inventory_items = relationship("BarInventory", back_populates="bar", cascade="all, delete-orphan")
    sales = relationship("BarSale", back_populates="bar", cascade="all, delete-orphan")
    issues = relationship("StoreIssue", back_populates="issued_to")  # ✅ Match the other side



# ----------------------------
# Bar Inventory
# ----------------------------
class BarInventory(Base):
    __tablename__ = "bar_inventory"

    id = Column(Integer, primary_key=True, index=True)
    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=False)
    bar_name = Column(String, nullable=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    item_name = Column(String)
    quantity = Column(Integer, default=0, nullable=False)
    selling_price = Column(Float, default=0)
    received_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String, nullable=True)

    bar = relationship("Bar", back_populates="inventory_items")
    item = relationship("StoreItem")

    # ✅ Fixed relationship
    sale_items = relationship("BarSaleItem", back_populates="bar_inventory", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("bar_id", "item_id", name="unique_bar_item"),
    )


class BarInventoryAdjustment(Base):
    __tablename__ = "bar_inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    bar_id = Column(Integer, ForeignKey("bars.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False)
    quantity_adjusted = Column(Integer, nullable=False)  # e.g., 3 units removed
    reason = Column(String, nullable=True)  # Damaged, Expired, etc.
    adjusted_by = Column(String, nullable=True)
    adjusted_at = Column(DateTime, server_default=func.now())

    bar = relationship("Bar")
    item = relationship("StoreItem")



class BarInventoryReceipt(Base):
    __tablename__ = "bar_inventory_receipts"

    id = Column(Integer, primary_key=True, index=True)
    bar_id = Column(Integer, ForeignKey("bars.id"))
    bar_name = Column(String)
    item_id = Column(Integer, ForeignKey("store_items.id"))
    item_name = Column(String)
    quantity = Column(Integer)
    selling_price = Column(Float)
    received_at = Column(DateTime, default=datetime.utcnow)
    note = Column(String)
    created_by = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # ✅ Add this line

# ----------------------------
# Bar Sale
# ----------------------------
class BarSale(Base):
    __tablename__ = "bar_sales"

    id = Column(Integer, primary_key=True, index=True)
    bar_id = Column(Integer, ForeignKey("bars.id"))
    created_by_id = Column(Integer, ForeignKey("users.id"))
    sale_date = Column(DateTime, default=datetime.utcnow)
    total_amount = Column(Float, default=0.0)
    status = Column(String, default="completed")  # <- Status now included
    #voided_at = Column(DateTime, nullable=True)

    bar = relationship("Bar", back_populates="sales")
    created_by_user = relationship("User", lazy="joined")

    payments = relationship("BarPayment", back_populates="bar_sale", cascade="all, delete-orphan")
    sale_items = relationship("BarSaleItem", back_populates="sale", cascade="all, delete-orphan")
    
    

    @property
    def created_by(self):
        return self.created_by_user.username if self.created_by_user else None




# ----------------------------
# Bar Sale Item
# ----------------------------
class BarSaleItem(Base):
    __tablename__ = "bar_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("bar_sales.id"), nullable=False)
    bar_inventory_id = Column(Integer, ForeignKey("bar_inventory.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)

    sale = relationship("BarSale", back_populates="sale_items")
    bar_inventory = relationship("BarInventory", back_populates="sale_items")

    
