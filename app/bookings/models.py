from sqlalchemy import event
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, DateTime, Float

from app.database import Base
from app.core.mixins import BusinessMixin
from app.core.timezone import now_wat  # ✅ centralized timezone


class Booking(Base, BusinessMixin):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # ----------------------------
    # Room رابطه (Multi-tenant safe)
    # ----------------------------
    room_id = Column(
        Integer,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False
    )

    room_number = Column(String, nullable=False)  # snapshot for history

    # ----------------------------
    # Guest Info
    # ----------------------------
    guest_name = Column(String, nullable=False)
    gender = Column(String, nullable=False)

    mode_of_identification = Column(String, nullable=True)
    identification_number = Column(String, nullable=True)

    address = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)

    # ----------------------------
    # Booking تفاصيل
    # ----------------------------
    arrival_date = Column(Date, nullable=False)
    departure_date = Column(Date, nullable=False)

    number_of_days = Column(Integer, nullable=False)

    room_price = Column(Float, nullable=False)
    booking_cost = Column(Float, nullable=True)

    booking_type = Column(String, nullable=False)
    status = Column(String, default="reserved")

    payment_status = Column(String, default="pending")

    # ----------------------------
    # Timezone FIX (WAT)
    # ----------------------------
    booking_date = Column(
        DateTime(timezone=True),
        nullable=False,
        default=now_wat   # ✅ FIXED (no inline ZoneInfo)
    )

    # ----------------------------
    # Extras
    # ----------------------------
    vehicle_no = Column(String, nullable=True)
    attachment = Column(String, nullable=True)

    is_checked_out = Column(Boolean, default=False)
    cancellation_reason = Column(String, nullable=True)
    deleted = Column(Boolean, default=False)

    created_by = Column(String, nullable=False)

    # ✅ Optional but VERY useful
    created_at = Column(DateTime(timezone=True), default=now_wat)
    updated_at = Column(DateTime(timezone=True), default=now_wat, onupdate=now_wat)

    # ----------------------------
    # Relationships
    # ----------------------------
    room = relationship("Room", back_populates="bookings")
    payments = relationship("Payment", back_populates="booking")


# ----------------------------
# Auto-calculate number_of_days
# ----------------------------
@event.listens_for(Booking, "before_insert")
@event.listens_for(Booking, "before_update")
def set_number_of_days(mapper, connection, target):
    if target.arrival_date and target.departure_date:
        target.number_of_days = (target.departure_date - target.arrival_date).days
