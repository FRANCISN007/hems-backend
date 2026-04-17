# app/business/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from sqlalchemy import func
from app.users.auth import get_current_user
from app.users.schemas import UserDisplaySchema
from app.license import models as license_models


from app.database import get_db
from app.business import models, schemas
from app.users.permissions import role_required

router = APIRouter()


# -------------------------------
# CREATE BUSINESS - ONLY SUPER ADMIN
# -------------------------------

@router.post("/", response_model=schemas.BusinessOut, status_code=201)
def create_business(
    business_in: schemas.BusinessCreate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin"], bypass_admin=False))
):
    """
    Super admin creates a new business.
    The owner_username is explicitly provided (the admin/owner of this business).
    """
    # Prevent duplicate business name
    existing = db.query(models.Business).filter(
        models.Business.name == business_in.name.strip()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Business name already exists")

    # Prevent duplicate owner_username for businesses (optional but recommended)
    existing_owner = db.query(models.Business).filter(
        models.Business.owner_username == business_in.owner_username.strip()
    ).first()
    if existing_owner:
        raise HTTPException(status_code=400, detail="This username is already used as owner for another business")

    # Create business with the specified owner_username
    business = models.Business(
        name=business_in.name.strip(),
        address=business_in.address,
        phone=business_in.phone,
        email=business_in.email,
        owner_username=business_in.owner_username.strip()  # ← from input, NOT current_user
    )

    db.add(business)
    db.commit()
    db.refresh(business)

    # Safe response with computed license_active
    biz_out = schemas.BusinessOut.from_orm(business)
    biz_out.license_active = business.is_license_active(db)
    # owner_username is already in biz_out from the column

    return biz_out



@router.get("/", response_model=schemas.BusinessListResponse)
def list_businesses(
    active: Optional[bool] = Query(
        None,
        description="Filter by license active status: true (active), false (inactive/expired)"
    ),
    name: Optional[str] = Query(
        None,
        description="Search/filter by business name (partial, case-insensitive)"
    ),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    List businesses with:
    - License active/inactive filter (?active=true/false)
    - Business name search (?name=xyz)
    - Sorted by ID in ascending order (Business 1, 2, 3...)
    - Real-time expiration_date from latest license
    - owner_username from DB column
    """
    roles = set(current_user.roles)

    if "super_admin" in roles:
        # Super admin sees ALL businesses
        query = db.query(models.Business)

        # Apply name search filter (partial, case-insensitive)
        if name:
            query = query.filter(
                func.lower(models.Business.name).ilike(f"%{name.lower().strip()}%")
            )

        # Apply active/inactive filter (computed from licenses)
        if active is not None:
            subquery = (
                db.query(license_models.LicenseKey.business_id)
                .filter(
                    license_models.LicenseKey.is_active == True,
                    license_models.LicenseKey.expiration_date >= datetime.utcnow()
                )
                .subquery()
            )

            if active:
                query = query.filter(models.Business.id.in_(subquery))
            else:
                query = query.filter(~models.Business.id.in_(subquery))

        # ✅ SORT BY ID ASCENDING (Business 1 first)
        query = query.order_by(models.Business.id.asc())

        businesses = query.all()

        enriched = []
        for biz in businesses:
            biz_out = schemas.BusinessOut.from_orm(biz)

            # Latest license for active status and expiration date
            latest_license = (
                db.query(license_models.LicenseKey)
                .filter(license_models.LicenseKey.business_id == biz.id)
                .order_by(license_models.LicenseKey.expiration_date.desc())
                .first()
            )

            biz_out.license_active = (
                latest_license.is_active and latest_license.expiration_date >= datetime.utcnow()
            ) if latest_license else False

            biz_out.expiration_date = latest_license.expiration_date if latest_license else None
            biz_out.owner_username = biz.owner_username

            enriched.append(biz_out)

        return {"total": len(enriched), "businesses": enriched}

    else:
        # Normal admin → only their own business
        business = (
            db.query(models.Business)
            .filter(models.Business.id == current_user.business_id)
            .first()
        )

        if not business:
            return {"total": 0, "businesses": []}

        # Apply name filter (only if it matches their business)
        if name and name.lower().strip() not in business.name.lower():
            return {"total": 0, "businesses": []}

        latest_license = (
            db.query(license_models.LicenseKey)
            .filter(license_models.LicenseKey.business_id == business.id)
            .order_by(license_models.LicenseKey.expiration_date.desc())
            .first()
        )

        is_active = (
            latest_license.is_active and latest_license.expiration_date >= datetime.utcnow()
        ) if latest_license else False

        if active is not None and is_active != active:
            return {"total": 0, "businesses": []}

        biz_out = schemas.BusinessOut.from_orm(business)
        biz_out.license_active = is_active
        biz_out.expiration_date = latest_license.expiration_date if latest_license else None
        biz_out.owner_username = business.owner_username

        return {
            "total": 1,
            "businesses": [biz_out]
        }



from typing import List, Optional
from fastapi import Query
from sqlalchemy import func

@router.get("/simple", response_model=List[schemas.BusinessSimple])
def list_businesses_simple(
    search: Optional[str] = Query(None, description="Search businesses by name"),
    limit: int = Query(50, ge=1, le=100, description="Max number of results"),
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Return a simple list of businesses for dropdowns:

    - Super admin → can search all businesses
    - Admin → only their own business
    - Returns only `id` and `name`
    """

    query = db.query(models.Business.id, models.Business.name)

    # Admin → only their own business
    if "super_admin" not in set(current_user.roles):
        query = query.filter(models.Business.id == current_user.business_id)
    else:
        # Super admin → apply optional search
        if search:
            search_term = f"%{search.strip().lower()}%"
            query = query.filter(func.lower(models.Business.name).ilike(search_term))

    return query.order_by(models.Business.name.asc()).limit(limit).all()

    

@router.get("/{business_id}", response_model=schemas.BusinessOut)
def get_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Get details of a single business by ID.
    
    - Regular users → only their own business
    - Super admin → any business
    - Includes license_active (computed) and expiration_date from latest license
    """
    # Fetch business
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Permission check
    roles = set(current_user.roles)
    if "super_admin" not in roles and business.id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Safe mapping from ORM
    biz_out = schemas.BusinessOut.from_orm(business)

    # Get latest license for active status and expiration date
    latest_license = (
        db.query(license_models.LicenseKey)
        .filter(license_models.LicenseKey.business_id == business.id)
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    biz_out.license_active = (
        latest_license.is_active and latest_license.expiration_date >= datetime.utcnow()
    ) if latest_license else False

    biz_out.expiration_date = latest_license.expiration_date if latest_license else None
    biz_out.owner_username = business.owner_username

    return biz_out


@router.put("/{business_id}", response_model=schemas.BusinessOut)
def update_business(
    business_id: int,
    updated: schemas.BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: UserDisplaySchema = Depends(role_required(["super_admin", "admin"]))
):
    """
    Update business details.
    
    - Super admin → any business
    - Admin → only their own business
    - Cannot change owner_username or business_id
    - Returns updated business with computed license_active and expiration_date
    """
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    roles = set(current_user.roles)
    if "super_admin" not in roles and business.id != current_user.business_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Apply updates (only allowed fields from schema)
    update_data = updated.dict(exclude_unset=True)

    # Prevent changing protected fields
    protected = {"owner_username", "business_id"}
    for field in protected:
        if field in update_data:
            raise HTTPException(status_code=400, detail=f"Cannot update '{field}'")

    for field, value in update_data.items():
        setattr(business, field, value)

    db.commit()
    db.refresh(business)

    # Safe mapping + computed fields
    biz_out = schemas.BusinessOut.from_orm(business)

    # Latest license for active status and expiration date
    latest_license = (
        db.query(license_models.LicenseKey)
        .filter(license_models.LicenseKey.business_id == business.id)
        .order_by(license_models.LicenseKey.expiration_date.desc())
        .first()
    )

    biz_out.license_active = (
        latest_license.is_active and latest_license.expiration_date >= datetime.utcnow()
    ) if latest_license else False

    biz_out.expiration_date = latest_license.expiration_date if latest_license else None
    biz_out.owner_username = business.owner_username

    return biz_out


from sqlalchemy.exc import IntegrityError

@router.delete("/{business_id}")
def delete_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(role_required(["super_admin", "admin"]))
):
    roles = set(current_user.roles)

    if "super_admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Only super admin can delete businesses"
        )

    business = db.query(models.Business).filter(
        models.Business.id == business_id
    ).first()

    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )

    try:
        db.delete(business)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete business because it has related records"
        )

    return {"message": f"Business {business.name} deleted successfully"}

