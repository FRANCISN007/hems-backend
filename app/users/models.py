from app.database import Base
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(50), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    roles = Column(String(200), default="user")

    # ✅ Allow NULL for super_admin
    business_id = Column(
        Integer,
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Optional relationship
    business = relationship("Business")
