from sqlalchemy.orm import Session
from app.rooms import models, schemas
from app.rooms import models as room_models

from datetime import datetime
from zoneinfo import ZoneInfo
def get_local_time():
    return datetime.now(ZoneInfo("Africa/Lagos"))



def create_room(db: Session, room: schemas.RoomSchema, business_id: int):

    new_room = room_models.Room(
        room_number=room.room_number,
        room_type=room.room_type,
        amount=room.amount,
        status=room.status,
        business_id=business_id,
        #created_at=get_local_time()
    )

    db.add(new_room)
    db.commit()
    db.refresh(new_room)

    return new_room





# crud.py

from sqlalchemy.orm import Session
from typing import List, Optional


def get_rooms_with_pagination(skip: int, limit: int, db: Session, business_id: Optional[int] = None) -> List[room_models.Room]:
    """
    Fetch rooms with pagination and optional business_id filter.
    """
    query = db.query(room_models.Room).order_by(room_models.Room.id.asc())

    if business_id:
        query = query.filter(room_models.Room.business_id == business_id)

    return query.offset(skip).limit(limit).all()


def serialize_rooms(rooms: List[room_models.Room]) -> List[dict]:
    """
    Convert Room SQLAlchemy objects (optionally joined with additional info)
    to JSON-serializable dicts.
    """
    serialized = []

    for room in rooms:
        if room.id is None:
            continue  # skip corrupted entries

        # Support dynamically added attributes (via joins/annotations)
        payment_status = getattr(room, "payment_status", None)
        future_reservation_count = getattr(room, "future_reservation_count", 0)

        serialized.append({
            "id": room.id,
            "room_number": room.room_number,
            "room_type": room.room_type,
            "amount": room.amount,
            "status": room.status,
            #"payment_status": payment_status,
            "future_reservation_count": future_reservation_count,
        })

    return serialized



    

def get_total_room_count(db: Session):
    """
    Fetch the total number of rooms in the hotel.
    """
    return db.query(room_models.Room).count()
