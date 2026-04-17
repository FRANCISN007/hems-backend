from pydantic import BaseModel
from typing import List
from datetime import datetime
from typing import Optional
from typing import Literal
from decimal import Decimal
from datetime import date

        

class RoomSchema(BaseModel):
    room_number: str
    room_type: str
    amount: Decimal
    status: Literal["available", "maintenance"] = "available"
    business_id: Optional[int] = None  # Only used by super_admin

    class Config:
        from_attributes = True





class RoomFaultSchema(BaseModel):
    id: Optional[int] = None  # ✅ Add this to allow updating existing faults
    room_number: str
    description: str
    resolved: bool = False

    class Config:
        from_attributes = True
        

class RoomList(BaseModel):
    room_number: str
    room_type: str
    amount: float
    

    class Config:
        from_attributes = True
        
        
class RoomUpdateSchema(BaseModel):
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    amount: Optional[int] = None
    status: Optional[Literal["available", "checked-in", "reserved", "maintenance", "complimentary"]] = None
    faults: Optional[List[RoomFaultSchema]] = None  # ✅ Accept faults with optional IDs

    class Config:
        from_attributes = True



class RoomFaultOut(BaseModel):
    id: int
    room_number: str
    description: str
    resolved: bool
    created_at: datetime  # include time and timezone
    resolved_at: Optional[datetime] = None  # changed here

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M') if v else None
        }



class FaultUpdate(BaseModel):
    id: int
    resolved: bool


class RoomStatusUpdate(BaseModel):
    status: str

class RoomOut(BaseModel):
    id: int
    room_number: str
    room_type: str
    amount: float
    status: Literal["available", "maintenance"]
    has_future_reservation: bool = False  # ✅ Add this
    future_reservation_count: int = 0  # ✅ Add this line


    class Config:
        from_attributes = True




class RoomListResponse(BaseModel):
    total_rooms: int
    rooms: List[RoomOut]

    class Config:
        from_attributes = True
