# app/vendors/models.py

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.mixins import BusinessMixin


class Vendor(Base, BusinessMixin):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)

    purchases = relationship("StoreStockEntry", back_populates="vendor")
