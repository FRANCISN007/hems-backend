from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import Base
from app.core.mixins import BusinessMixin



class EventPayment(Base, BusinessMixin):
    __tablename__ = "event_payments"

    id = Column(Integer, primary_key=True, index=True)

    event_id = Column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False
    )

    

    organiser = Column(String, index=True, nullable=False)

    event_amount = Column(Float, nullable=False)

    amount_paid = Column(Float, nullable=False)

    discount_allowed = Column(Float, default=0.0)

    balance_due = Column(Float, default=0.0)

    payment_method = Column(String, nullable=False)

    # bank name (can later become bank_id)
    bank = Column(String, nullable=True)

    payment_date = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(ZoneInfo("Africa/Lagos"))
    )

    payment_status = Column(String, default="pending")

    created_by = Column(String, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(ZoneInfo("UTC"))
    )

    # Relationships
    event = relationship("Event", back_populates="payments")

    

    def compute_balance_due(self):
        if self.event:
            self.balance_due = (
                self.event.event_amount
                - (self.amount_paid + self.discount_allowed)
            )
