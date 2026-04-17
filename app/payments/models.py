from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.mixins import BusinessMixin
from app.core.timezone import now_wat  # ✅ use centralized timezone


class Payment(Base, BusinessMixin):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    # -------------------------------
    # Relationships
    # -------------------------------
    booking_id = Column(
        Integer,
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    room_number = Column(String, index=True)
    guest_name = Column(String, index=True)

    # -------------------------------
    # Financials
    # -------------------------------
    amount_paid = Column(Float, nullable=False, default=0.0)
    discount_allowed = Column(Float, default=0.0)
    balance_due = Column(Float, default=0.0)

    # -------------------------------
    # Payment Info
    # -------------------------------
    payment_method = Column(String, nullable=False)

    # ✅ FIXED: use WAT timezone
    payment_date = Column(
        DateTime(timezone=True),
        default=now_wat
    )

    void_date = Column(
        DateTime(timezone=True),
        nullable=True
    )

    status = Column(String, default="pending")

    created_by = Column(String, nullable=False)

    # -------------------------------
    # Bank رابطه
    # -------------------------------
    bank_id = Column(
        Integer,
        ForeignKey("banks.id", ondelete="RESTRICT"),
        nullable=True
    )

    bank = relationship("Bank", back_populates="payments")

    # -------------------------------
    # Booking relationship
    # -------------------------------
    booking = relationship("Booking", back_populates="payments")
