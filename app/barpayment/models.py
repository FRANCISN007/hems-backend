from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import Base
from app.core.mixins import BusinessMixin


class BarPayment(Base, BusinessMixin):
    __tablename__ = "bar_payments"

    id = Column(Integer, primary_key=True, index=True)

    bar_sale_id = Column(
        Integer,
        ForeignKey("bar_sales.id", ondelete="CASCADE"),
        nullable=False
    )

    

    amount_paid = Column(Float, nullable=False)

    payment_method = Column(String, nullable=False)

    bank = Column(String, nullable=True)

    date_paid = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    received_by_id = Column(Integer, ForeignKey("users.id"))

    status = Column(String, default="active")

    created_by = Column(String)

    note = Column(String, nullable=True)

    # Relationships
    bar_sale = relationship("BarSale", back_populates="payments")

    received_by_user = relationship("User", lazy="joined")

    