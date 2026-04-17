from sqlalchemy import Column, Integer, String, Float, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import pytz
from app.core.mixins import BusinessMixin


def get_local_time():
    lagos_tz = pytz.timezone("Africa/Lagos")
    return datetime.now(lagos_tz)


# Event Model
class Event(Base, BusinessMixin):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)

    
    organizer = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)

    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)

    event_amount = Column(Float, nullable=False)
    caution_fee = Column(Float, nullable=False)

    location = Column(String, nullable=True)
    phone_number = Column(String, nullable=False)
    address = Column(String, nullable=False)

    payment_status = Column(String, default="active")
    balance_due = Column(Float, nullable=False, default=0)

    created_by = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=get_local_time)
    updated_at = Column(DateTime(timezone=True), default=get_local_time, onupdate=get_local_time)

    cancellation_reason = Column(String, nullable=True)

    # Relationships
    
    payments = relationship(
        "EventPayment",
        back_populates="event",
        cascade="all, delete",
        lazy="joined"
    )
