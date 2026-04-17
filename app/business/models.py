# app/business/models.py

from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship, Session

from app.database import Base

LAGOS_TZ = ZoneInfo("Africa/Lagos")


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)

    # Basic info
    name = Column(String, nullable=False, unique=True, index=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # creator / admin username
    owner_username = Column(String, nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(LAGOS_TZ),
        nullable=False
    )

    # -----------------------------
    # CORE SYSTEM RELATIONSHIPS
    # -----------------------------

    users = relationship(
        "User",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    licenses = relationship(
        "LicenseKey",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # FINANCE
    # -----------------------------

    banks = relationship(
        "Bank",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    payments = relationship(
        "Payment",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # VENDORS
    # -----------------------------

    vendors = relationship(
        "Vendor",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # STORE / INVENTORY
    # -----------------------------

    store_categories = relationship(
        "StoreCategory",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_items = relationship(
        "StoreItem",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_stock_entries = relationship(
        "StoreStockEntry",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_issues = relationship(
        "StoreIssue",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_issue_items = relationship(
        "StoreIssueItem",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_inventory = relationship(
        "StoreInventory",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    store_inventory_adjustments = relationship(
        "StoreInventoryAdjustment",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # RESTAURANT
    # -----------------------------

    restaurant_locations = relationship(
        "RestaurantLocation",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    meal_categories = relationship(
        "MealCategory",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    meals = relationship(
        "Meal",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    meal_orders = relationship(
        "MealOrder",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    restaurant_sales = relationship(
        "RestaurantSale",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    restaurant_sale_payments = relationship(
        "RestaurantSalePayment",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # ROOMS
    # -----------------------------

    rooms = relationship(
        "Room",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    room_faults = relationship(
        "RoomFault",
        back_populates="business",
        cascade="all, delete-orphan"
    )

    # -----------------------------
    # LICENSE CHECK
    # -----------------------------

    def is_license_active(self, db: Session) -> bool:
        """
        Check if the business has an active non-expired license
        """
        from app.license.models import LicenseKey

        latest_license = (
            db.query(LicenseKey)
            .filter(
                LicenseKey.business_id == self.id,
                LicenseKey.is_active == True
            )
            .order_by(LicenseKey.expiration_date.desc())
            .first()
        )

        if not latest_license:
            return False

        return latest_license.expiration_date >= datetime.now(LAGOS_TZ)


# Import AFTER model declaration
from app.bank.models import Bank
from app.vendor.models import Vendor
from app.license.models import LicenseKey
from app.users.models import User
