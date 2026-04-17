from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.mixins import BusinessMixin


class Kitchen(Base, BusinessMixin):
    __tablename__ = "kitchens"

    id = Column(Integer, primary_key=True, index=True)

   

    name = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_kitchen_business_name"),
    )

    
    inventories = relationship("KitchenInventory", back_populates="kitchen", cascade="all, delete")
    issues = relationship("StoreIssue", back_populates="kitchen")
    stocks = relationship("KitchenStock", back_populates="kitchen")
    adjustments = relationship("KitchenInventoryAdjustment", back_populates="kitchen")


class KitchenInventory(Base, BusinessMixin):
    __tablename__ = "kitchen_inventories"

    id = Column(Integer, primary_key=True, index=True)

    

    kitchen_id = Column(Integer, ForeignKey("kitchens.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False, index=True)

    quantity = Column(Float, default=0, nullable=False)

    
    kitchen = relationship("Kitchen", back_populates="inventories")
    item = relationship("StoreItem")

    __table_args__ = (
        UniqueConstraint("business_id", "kitchen_id", "item_id", name="uq_kitchen_inventory"),
    )


class KitchenStock(Base, BusinessMixin):
    """
    Used for tracking historical usage:
    - total issued to kitchen
    - total used/sold in meals
    Helps for analysis and reporting.
    """
    __tablename__ = "kitchen_stock"

    id = Column(Integer, primary_key=True, index=True)

    

    kitchen_id = Column(Integer, ForeignKey("kitchens.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False, index=True)

    total_issued = Column(Float, default=0, nullable=False)
    total_used = Column(Float, default=0, nullable=False)

    
    kitchen = relationship("Kitchen", back_populates="stocks")
    item = relationship("StoreItem")

    __table_args__ = (
        UniqueConstraint("business_id", "kitchen_id", "item_id", name="uq_kitchen_stock"),
    )


class KitchenInventoryAdjustment(Base, BusinessMixin):
    __tablename__ = "kitchen_inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)

    

    kitchen_id = Column(Integer, ForeignKey("kitchens.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False, index=True)

    quantity_adjusted = Column(Float, nullable=False)
    reason = Column(String, nullable=True)

    adjusted_by = Column(String, nullable=False)

    adjusted_at = Column(DateTime(timezone=True), server_default=func.now())

    
    kitchen = relationship("Kitchen", back_populates="adjustments")
    item = relationship("StoreItem")


class KitchenMenu(Base, BusinessMixin):
    __tablename__ = "kitchen_menu"

    id = Column(Integer, primary_key=True, index=True)

    

    item_id = Column(Integer, ForeignKey("store_items.id"), nullable=False, index=True)
    selling_price = Column(Float, nullable=False)

    
    item = relationship("StoreItem")

    __table_args__ = (
        UniqueConstraint("business_id", "item_id", name="uq_kitchen_menu"),
    )
