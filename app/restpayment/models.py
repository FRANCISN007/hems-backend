from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Date
from sqlalchemy.orm import relationship

from app.database import Base
from app.core.mixins import BusinessMixin
from app.core.timezone import now_wat  # ✅ central timezone helper


class RestaurantSalePayment(Base, BusinessMixin):
    __tablename__ = "restaurant_sale_payments"

    id = Column(Integer, primary_key=True, index=True)

    sale_id = Column(Integer, ForeignKey("restaurant_sales.id"), nullable=False)

    amount_paid = Column(Float, nullable=False)

    payment_mode = Column(String, nullable=False)  # cash / pos / transfer

    bank = Column(String, nullable=True)

    paid_by = Column(String, nullable=True)

    # ✅ Business reporting date (very correct design)
    payment_date = Column(Date, nullable=False)

    # ✅ Timezone-aware timestamps (aligned with your system)
    created_at = Column(DateTime(timezone=True), default=now_wat, nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        default=now_wat,
        onupdate=now_wat,
        nullable=False
    )

    is_void = Column(Boolean, default=False, nullable=False)

    # Relationships
    sale = relationship("RestaurantSale", back_populates="payments")
