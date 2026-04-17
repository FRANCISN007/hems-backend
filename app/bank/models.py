from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base
from app.core.mixins import BusinessMixin


class Bank(Base, BusinessMixin):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    # Prevent duplicate bank names inside the same business
    __table_args__ = (
        UniqueConstraint("business_id", "name", name="uq_bank_business_name"),
    )

    # payments relationship
    payments = relationship("Payment", back_populates="bank")
