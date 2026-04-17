# app/vendors/router.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

from app.database import get_db
from app.vendor import models, schemas
from app.users.schemas import UserDisplaySchema
from app.users.permissions import role_required
from app.core.business import resolve_business_id

router = APIRouter()


# ---------------------------------------------------
# HELPER: Get Vendor Scoped To Business
# ---------------------------------------------------
def get_business_vendor(db: Session, vendor_id: int, business_id: int):
    vendor = db.query(models.Vendor).filter(
        models.Vendor.id == vendor_id,
        models.Vendor.business_id == business_id
    ).first()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    return vendor


# ---------------------------------------------------
# HELPER: Normalize Vendor Input
# ---------------------------------------------------
def normalize_vendor_data(vendor):
    name = (vendor.business_name or "").strip()
    address = (vendor.address or "").strip()
    phone = (vendor.phone_number or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Vendor name is required")

    return name, address, phone, name.lower()


# ---------------------------------------------------
# CREATE VENDOR
# ---------------------------------------------------
@router.post("/", response_model=schemas.VendorOut)
def create_vendor(
    vendor: schemas.VendorCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "store"]))
):
    business_id = resolve_business_id(current_user, business_id)

    name, address, phone, normalized_name = normalize_vendor_data(vendor)

    # ✅ Duplicate check
    existing = db.query(models.Vendor).filter(
        models.Vendor.business_id == business_id,
        func.lower(models.Vendor.business_name) == normalized_name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Vendor name already exists for this business"
        )

    new_vendor = models.Vendor(
        business_name=name,
        address=address,
        phone_number=phone,
        business_id=business_id
    )

    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)

    return new_vendor


# ---------------------------------------------------
# SIMPLE LIST (FOR DROPDOWNS)
# ---------------------------------------------------
@router.get("/simple")
def list_vendors_simple(
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["dashboard", "admin", "store"]))
):
    business_id = resolve_business_id(current_user, business_id)

    vendors = db.query(
        models.Vendor.id,
        models.Vendor.business_name
    ).filter(
        models.Vendor.business_id == business_id
    ).order_by(
        models.Vendor.business_name.asc()
    ).all()

    return [{"id": v.id, "name": v.business_name} for v in vendors]


# ---------------------------------------------------
# LIST VENDORS
# ---------------------------------------------------
@router.get("/", response_model=List[schemas.VendorOut])
def list_vendors(
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["dashboard", "admin", "store"]))
):
    business_id = resolve_business_id(current_user, business_id)

    return db.query(models.Vendor).filter(
        models.Vendor.business_id == business_id
    ).order_by(
        models.Vendor.business_name.asc()
    ).all()


# ---------------------------------------------------
# GET SINGLE VENDOR
# ---------------------------------------------------
@router.get("/{vendor_id}", response_model=schemas.VendorOut)
def get_vendor(
    vendor_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["dashboard", "admin", "store"]))
):
    business_id = resolve_business_id(current_user, business_id)
    return get_business_vendor(db, vendor_id, business_id)


# ---------------------------------------------------
# UPDATE VENDOR
# ---------------------------------------------------
@router.put("/{vendor_id}", response_model=schemas.VendorOut)
def update_vendor(
    vendor_id: int,
    updated_data: schemas.VendorCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin", "store"]))
):
    business_id = resolve_business_id(current_user, business_id)

    vendor = get_business_vendor(db, vendor_id, business_id)

    name, address, phone, normalized_name = normalize_vendor_data(updated_data)

    # ✅ Duplicate check (excluding current vendor)
    duplicate = db.query(models.Vendor).filter(
        models.Vendor.business_id == business_id,
        func.lower(models.Vendor.business_name) == normalized_name,
        models.Vendor.id != vendor_id
    ).first()

    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="Vendor name already exists for this business"
        )

    vendor.business_name = name
    vendor.address = address
    vendor.phone_number = phone

    db.commit()
    db.refresh(vendor)

    return vendor


# ---------------------------------------------------
# DELETE VENDOR
# ---------------------------------------------------
@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["admin"]))
):
    business_id = resolve_business_id(current_user, business_id)

    vendor = get_business_vendor(db, vendor_id, business_id)

    if vendor.purchases:
        raise HTTPException(
            status_code=400,
            detail="Vendor cannot be deleted because it is linked to purchases"
        )

    db.delete(vendor)
    db.commit()

    return {"detail": "Vendor deleted successfully"}
