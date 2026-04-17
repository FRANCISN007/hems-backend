from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.users import schemas as user_schemas

from app.core.db import db_dependency
from app.core.business import resolve_business_id
from app.users.permissions import role_required  # 👈 permission helper

from app.users.schemas import UserDisplaySchema
from app.importitem import service 



router = APIRouter()


# ------------------- IMPORT STORE ITEMS -------------------
@router.post("/import-excel")
def import_from_excel(
    file: UploadFile = File(...),
    business_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(
        role_required(["super_admin"])
    ),
):
    return service.import_from_excel(
        db, file, current_user, business_id
    )
