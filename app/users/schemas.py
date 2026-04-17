from pydantic import BaseModel
from typing import List, Optional
from typing import Literal
from datetime import date
from pydantic import validator


# -------- USERS --------
# -------- USERS --------
class UserSchema(BaseModel):
    username: str
    password: str
    roles: List[str] = ["user"]
    admin_password: Optional[str] = None
    business_id: Optional[int] = None  # ✅ Link user to a business

    @validator("roles", pre=True, always=True)
    def ensure_roles(cls, v):
        if not v:
            return ["user"]
        return v



class BusinessInfo(BaseModel):
    id: Optional[int]
    name: Optional[str]



class UserUpdateSchema(BaseModel):
    password: Optional[str] = None
    roles: Optional[List[str]] = None


class UserDisplaySchema(BaseModel):
    id: int
    username: str
    roles: List[str] = []
    business_id: Optional[int] = None   # ← ADD THIS
    business_name: Optional[str] = None   # ← ADD THIS


    @validator("roles", pre=True)
    def ensure_roles_list(cls, v):
        # Normalize: None -> empty list, "a,b" -> ["a","b"], list -> stripped strings
        if v is None:
            return []
        if isinstance(v, str):
            return [r.strip() for r in v.split(",") if r.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        # fallback
        return []


    class Config:
        from_attributes = True



# -------- SUPER ADMIN --------
class SuperAdminCreate(BaseModel):
    username: str
    password: str
    admin_license_password: str




class SuperAdminUpdate(BaseModel):
    username: str
    new_password: str
    admin_license_password: str
