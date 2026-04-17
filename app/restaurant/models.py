from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.mixins import BusinessMixin
from app.core.timezone import now_wat  # ✅ USE YOUR CENTRAL HELPER


# ----------------------------
# Restaurant Location
# ----------------------------
class RestaurantLocation(Base, BusinessMixin):
    __tablename__ = "restaurant_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_restaurant_location_name"),
    )


# ----------------------------
# Meal Category
# ----------------------------
class MealCategory(Base, BusinessMixin):
    __tablename__ = "meal_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_meal_category_name"),
    )


# ----------------------------
# Meal
# ----------------------------
class Meal(Base, BusinessMixin):
    __tablename__ = "meals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    available = Column(Boolean, default=True)

    category_id = Column(Integer, ForeignKey("meal_categories.id"))
    location_id = Column(Integer, ForeignKey("restaurant_locations.id"))

    category = relationship("MealCategory")
    location = relationship("RestaurantLocation")

    store_links = relationship("MealStoreItem", back_populates="meal")
    order_items = relationship("MealOrderItem", back_populates="meal")


# ----------------------------
# Meal Order
# ----------------------------
class MealOrder(Base, BusinessMixin):
    __tablename__ = "meal_orders"

    id = Column(Integer, primary_key=True, index=True)

    order_type = Column(String, nullable=False)
    guest_name = Column(String, nullable=False)
    room_number = Column(String, nullable=True)

    location_id = Column(Integer, ForeignKey("restaurant_locations.id"))
    kitchen_id = Column(Integer, ForeignKey("kitchens.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), default=now_wat)  # ✅ FIXED
    status = Column(String, default="open")

    created_by = Column(Integer, ForeignKey("users.id"))

    location = relationship("RestaurantLocation")
    kitchen = relationship("Kitchen")

    items = relationship(
        "MealOrderItem",
        back_populates="order",
        cascade="all, delete-orphan"
    )

    sale = relationship(
        "RestaurantSale",
        back_populates="order",
        uselist=False
    )


# ----------------------------
# Meal Order Item
# ----------------------------
class MealOrderItem(Base, BusinessMixin):
    __tablename__ = "meal_order_items"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(Integer, ForeignKey("meal_orders.id"))
    meal_id = Column(Integer, ForeignKey("meals.id"), nullable=True)
    store_item_id = Column(Integer, ForeignKey("store_items.id"))

    quantity = Column(Integer, nullable=False)
    store_qty_used = Column(Integer, nullable=False)

    item_name = Column(String, nullable=False)
    price_per_unit = Column(Float, nullable=False, default=0.0)
    total_price = Column(Float, nullable=False, default=0.0)

    order = relationship("MealOrder", back_populates="items")
    meal = relationship("Meal", back_populates="order_items")
    store_item = relationship("StoreItem", back_populates="meal_order_items")


# ----------------------------
# Restaurant Sale
# ----------------------------
class RestaurantSale(Base, BusinessMixin):
    __tablename__ = "restaurant_sales"

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(Integer, ForeignKey("meal_orders.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("restaurant_locations.id"), nullable=False)

    guest_name = Column(String, nullable=True)
    served_by = Column(String, nullable=False)

    total_amount = Column(Float, nullable=False)
    status = Column(String, default="unpaid")

    served_at = Column(DateTime(timezone=True), default=now_wat)   # ✅ FIXED
    created_at = Column(DateTime(timezone=True), default=now_wat)  # ✅ FIXED

    order = relationship("MealOrder", back_populates="sale")

    payments = relationship(
        "RestaurantSalePayment",
        back_populates="sale",
        cascade="all, delete"
    )


# ----------------------------
# Meal Store Item
# ----------------------------
class MealStoreItem(Base, BusinessMixin):
    __tablename__ = "meal_store_items"

    id = Column(Integer, primary_key=True, index=True)

    meal_id = Column(Integer, ForeignKey("meals.id"))
    store_item_id = Column(Integer, ForeignKey("store_items.id"))

    quantity_used = Column(Float, default=1)

    meal = relationship("Meal", back_populates="store_links")
    store_item = relationship("StoreItem")
