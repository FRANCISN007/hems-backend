from app.database import Base
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import pytz
from app.core.mixins import BusinessMixin

def get_local_time():
    """Return current time in Africa/Lagos timezone"""
    lagos_tz = pytz.timezone("Africa/Lagos")
    return datetime.now(lagos_tz)


class Room(Base, BusinessMixin):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String, nullable=False, unique=True)  # ensure unique for FK reference
    room_type = Column(String(50))
    amount = Column(Integer)
    status = Column(String(50))  # "available" or "maintenance"

    # Relationships
    bookings = relationship("Booking", back_populates="room", cascade="all, delete-orphan")
    faults = relationship(
        "RoomFault",
        back_populates="room",
        cascade="all, delete-orphan"
    )


class RoomFault(Base, BusinessMixin):
    __tablename__ = "room_faults"

    id = Column(Integer, primary_key=True, index=True)
    
    # FK to Room.id ensures proper referential integrity
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    
    # Optional historical room_number for display purposes
    room_number = Column(String, nullable=True)

    description = Column(String, nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=get_local_time)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship back to Room
    room = relationship(
        "Room",
        back_populates="faults"
    )
