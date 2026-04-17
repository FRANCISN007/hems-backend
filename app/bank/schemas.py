from pydantic import BaseModel

class BankBase(BaseModel):
    name: str

class BankCreate(BankBase):
    pass

class BankUpdate(BankBase):
    pass

class BankDisplay(BankBase):
    id: int

    class Config:
        from_attributes = True
