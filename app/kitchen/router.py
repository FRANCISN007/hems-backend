from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.users.permissions import role_required  # 👈 permission helper
from sqlalchemy import func

from app.database import get_db
from app.kitchen.models import Kitchen, KitchenInventory, KitchenStock, KitchenMenu, KitchenInventoryAdjustment
from app.kitchen.schemas import KitchenCreate, KitchenDisplaySimple, KitchenMenuDisplay, KitchenMenuCreate, KitchenMenuUpdate
from app.kitchen.schemas import KitchenInventoryAdjustmentCreate, KitchenInventoryAdjustmentDisplay
from app.store.models import StoreItem
from app.users.schemas import UserDisplaySchema

from app.kitchen import models as kitchen_models
from app.kitchen import schemas as kitchen_schemas
from app.store import models as store_models


from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from app.core.timezone import now_wat, to_wat

from app.users import schemas as user_schemas

from app.core.db import db_dependency
from app.core.business import resolve_business_id





router = APIRouter()





# ----------------------------
# Create Kitchen (FINAL CLEAN)
# ----------------------------
@router.post("/", response_model=KitchenDisplaySimple)
def create_kitchen(
    data: KitchenCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        resolved_business_id = resolve_business_id(current_user, business_id)

        kitchen_name_clean = data.name.strip().lower()

        # ------------------------------
        # 2️⃣ Tenant-safe duplicate check 🔥
        # ------------------------------
        existing = (
            db.query(kitchen_models.Kitchen)
            .filter(
                kitchen_models.Kitchen.business_id == resolved_business_id,
                func.lower(kitchen_models.Kitchen.name) == kitchen_name_clean
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Kitchen '{data.name}' already exists for this business."
            )

        # ------------------------------
        # 3️⃣ Create kitchen
        # ------------------------------
        kitchen = kitchen_models.Kitchen(
            name=data.name.strip(),
            business_id=resolved_business_id
        )

        db.add(kitchen)
        db.commit()
        db.refresh(kitchen)

        return kitchen

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create kitchen: {str(e)}"
        )



# ----------------------------
# List Kitchens (FINAL CLEAN VERSION)
# ----------------------------
@router.get("/", response_model=List[KitchenDisplaySimple])
def list_kitchens(
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["store", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        resolved_business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ STRICT tenant filter 🔥
        # ------------------------------
        kitchens = (
            db.query(kitchen_models.Kitchen)
            .filter(kitchen_models.Kitchen.business_id == resolved_business_id)
            .order_by(kitchen_models.Kitchen.id.asc())
            .all()
        )

        return kitchens

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch kitchens: {str(e)}"
        )


# kitchen/router.py

# ----------------------------
# Kitchen Inventory Simple (FIXED - SAME PATTERN AS list_kitchens)
# ----------------------------
@router.get(
    "/inventory/simple",
    response_model=List[kitchen_schemas.KitchenInventorySimple]
)
def list_kitchen_inventory_simple(
    kitchen_id: int = Query(
        ...,
        description="Kitchen ID"
    ),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(db_dependency),  # 🔥 MUST use this (NOT get_db)
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "store", "kitchen", "super_admin"])
    )
):
    # ------------------------------
    # 1️⃣ Resolve business (same pattern as list_kitchens)
    # ------------------------------
    resolve_business_id(current_user, business_id)

    # ------------------------------
    # 2️⃣ Fetch kitchen (no manual tenant filtering here)
    # ------------------------------
    kitchen = (
        db.query(kitchen_models.Kitchen)
        .filter(kitchen_models.Kitchen.id == kitchen_id)
        .first()
    )

    if not kitchen:
        raise HTTPException(status_code=404, detail="Kitchen not found")

    # ------------------------------
    # 3️⃣ Fetch inventory (tenant handled globally)
    # ------------------------------
    inventory = (
        db.query(kitchen_models.KitchenInventory)
        .filter(kitchen_models.KitchenInventory.kitchen_id == kitchen_id)
        .order_by(kitchen_models.KitchenInventory.id.asc())
        .all()
    )

    # ------------------------------
    # 4️⃣ Response
    # ------------------------------
    return [
        kitchen_schemas.KitchenInventorySimple(
            id=inv.item_id,
            name=inv.item.name if inv.item else "",
            unit=inv.item.unit if inv.item else "",
            quantity=float(inv.quantity or 0)
        )
        for inv in inventory
    ]


# ----------------------------
# List kitchens for dropdowns (simple)
# ----------------------------
@router.get("/simple", response_model=List[KitchenDisplaySimple])
def list_kitchens_simple(
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["store", "admin", "super_admin"])
    )
):
    """
    Return a simplified list of kitchens (id + name) for dropdowns.
    Multi-tenant secured.
    """

    # ✅ Resolve tenant (STRICT)
    resolved_business_id = resolve_business_id(current_user, business_id)

    # ✅ Query ONLY this business
    kitchens = (
        db.query(kitchen_models.Kitchen)
        .filter(kitchen_models.Kitchen.business_id == resolved_business_id)
        .order_by(kitchen_models.Kitchen.id.asc())
        .all()
    )

    return kitchens




# ----------------------------
# Update Kitchen
# ----------------------------
@router.put("/{kitchen_id}", response_model=KitchenDisplaySimple)
def update_kitchen(
    kitchen_id: int,
    data: KitchenCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["admin" , "store"]))
):
    business_id = resolve_business_id(current_user, business_id)

    kitchen = db.query(kitchen_models.Kitchen).filter(
        kitchen_models.Kitchen.id == kitchen_id,
        kitchen_models.Kitchen.business_id == business_id
    ).first()

    if not kitchen:
        raise HTTPException(status_code=404, detail="Kitchen not found.")

    existing = db.query(kitchen_models.Kitchen).filter(
        kitchen_models.Kitchen.name == data.name,
        kitchen_models.Kitchen.business_id == business_id,
        kitchen_models.Kitchen.id != kitchen_id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Another kitchen with name '{data.name}' already exists."
        )

    kitchen.name = data.name

    db.commit()
    db.refresh(kitchen)

    return kitchen


# ----------------------------
# Delete Kitchen
# ----------------------------
@router.delete("/{kitchen_id}")
def delete_kitchen(
    kitchen_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["admin"]))
):
    business_id = resolve_business_id(current_user, business_id)

    kitchen = db.query(kitchen_models.Kitchen).filter(
        kitchen_models.Kitchen.id == kitchen_id,
        kitchen_models.Kitchen.business_id == business_id
    ).first()

    if not kitchen:
        raise HTTPException(status_code=404, detail="Kitchen not found.")

    has_inventory = db.query(KitchenInventory).filter(
        KitchenInventory.kitchen_id == kitchen_id,
        KitchenInventory.business_id == business_id
    ).first()

    has_stock = db.query(KitchenStock).filter(
        KitchenStock.kitchen_id == kitchen_id,
        KitchenStock.business_id == business_id
    ).first()

    if has_inventory or has_stock:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete kitchen '{kitchen.name}' because it has existing inventory or stock."
        )

    db.delete(kitchen)
    db.commit()

    return {"detail": f"Kitchen '{kitchen.name}' deleted successfully."}






# -------------------------
# Create kitchen adjustment (SIGN-BASED SYSTEM)
# -------------------------
@router.post(
    "/adjust",
    response_model=kitchen_schemas.KitchenInventoryAdjustmentDisplay
)
def adjust_kitchen_inventory(
    adjustment_data: kitchen_schemas.KitchenInventoryAdjustmentCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "store",  "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Validate inventory
        # ------------------------------
        inventory = (
            db.query(kitchen_models.KitchenInventory)
            .filter(
                kitchen_models.KitchenInventory.kitchen_id == adjustment_data.kitchen_id,
                kitchen_models.KitchenInventory.item_id == adjustment_data.item_id,
                kitchen_models.KitchenInventory.business_id == business_id
            )
            .first()
        )

        if not inventory:
            raise HTTPException(
                status_code=404,
                detail="Item not found in kitchen inventory"
            )

        qty = float(adjustment_data.quantity_adjusted)

        # ------------------------------
        # 3️⃣ APPLY SIGN LOGIC
        # ------------------------------
        new_quantity = inventory.quantity + qty

        # prevent negative stock
        if new_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Insufficient stock for this adjustment"
            )

        inventory.quantity = new_quantity

        # ------------------------------
        # 4️⃣ LOG ADJUSTMENT
        # ------------------------------
        adjustment = kitchen_models.KitchenInventoryAdjustment(
            kitchen_id=adjustment_data.kitchen_id,
            item_id=adjustment_data.item_id,
            quantity_adjusted=qty,  # keep signed value
            reason=adjustment_data.reason,
            adjusted_by=current_user.username,
            adjusted_at=now_wat(),
            business_id=business_id
        )

        db.add(adjustment)

        # ------------------------------
        # 5️⃣ UPDATE STOCK SUMMARY
        # ------------------------------
        stock = (
            db.query(kitchen_models.KitchenStock)
            .filter(
                kitchen_models.KitchenStock.kitchen_id == adjustment_data.kitchen_id,
                kitchen_models.KitchenStock.item_id == adjustment_data.item_id,
                kitchen_models.KitchenStock.business_id == business_id
            )
            .first()
        )

        if not stock:
            stock = kitchen_models.KitchenStock(
                kitchen_id=adjustment_data.kitchen_id,
                item_id=adjustment_data.item_id,
                total_issued=0,
                total_used=0,
                business_id=business_id
            )
            db.add(stock)

        # ------------------------------
        # 6️⃣ SIGN-BASED STOCK TRACKING
        # ------------------------------
        if qty < 0:
            # negative = used stock
            stock.total_used += abs(qty)
        else:
            # positive = returned/restocked
            stock.total_used -= qty
            if stock.total_used < 0:
                stock.total_used = 0

        # ------------------------------
        # 7️⃣ COMMIT
        # ------------------------------
        db.commit()
        db.refresh(adjustment)

        # ------------------------------
        # 8️⃣ RESPONSE
        # ------------------------------
        return kitchen_schemas.KitchenInventoryAdjustmentDisplay(
            id=adjustment.id,
            kitchen_id=adjustment.kitchen_id,
            item=kitchen_schemas.KitchenItemMinimalDisplay(
                id=inventory.item.id,
                name=inventory.item.name
            ),
            quantity_adjusted=adjustment.quantity_adjusted,
            reason=adjustment.reason,
            adjusted_by=adjustment.adjusted_by,
            adjusted_at=adjustment.adjusted_at
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Kitchen adjustment failed: {str(e)}"
        )




# -------------------------
# List kitchen adjustments (MULTI-TENANT SAFE)
# -------------------------
@router.get(
    "/adjustments",
    response_model=List[kitchen_schemas.KitchenInventoryAdjustmentDisplay]
)
def list_kitchen_inventory_adjustments(
    kitchen_id: Optional[int] = Query(None),
    item_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["store", "admin", "super_admin"])
    )
):
    business_id = resolve_business_id(current_user, business_id)

    query = (
        db.query(kitchen_models.KitchenInventoryAdjustment)
        .filter(kitchen_models.KitchenInventoryAdjustment.business_id == business_id)
        .order_by(kitchen_models.KitchenInventoryAdjustment.adjusted_at.desc())
    )

    if kitchen_id:
        query = query.filter(kitchen_models.KitchenInventoryAdjustment.kitchen_id == kitchen_id)

    if item_id:
        query = query.filter(kitchen_models.KitchenInventoryAdjustment.item_id == item_id)

    if start_date:
        query = query.filter(kitchen_models.KitchenInventoryAdjustment.adjusted_at >= start_date)

    if end_date:
        query = query.filter(kitchen_models.KitchenInventoryAdjustment.adjusted_at <= end_date)

    adjustments = query.all()

    return [
        kitchen_schemas.KitchenInventoryAdjustmentDisplay(
            id=adj.id,
            kitchen_id=adj.kitchen_id,
            item=kitchen_schemas.KitchenItemMinimalDisplay(
                id=adj.item_id,
                name=adj.item.name if adj.item else ""
            ),
            quantity_adjusted=adj.quantity_adjusted,
            reason=adj.reason,
            adjusted_by=adj.adjusted_by,
            adjusted_at=adj.adjusted_at
        )
        for adj in adjustments
    ]





# -------------------------
# Update kitchen adjustment (SIGN SAFE)
# -------------------------
@router.put(
    "/adjustments/{adjustment_id}",
    response_model=kitchen_schemas.KitchenInventoryAdjustmentDisplay
)
def update_kitchen_adjustment(
    adjustment_id: int,
    data: kitchen_schemas.KitchenInventoryAdjustmentCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "store", "super_admin"])
    )
):
    business_id = resolve_business_id(current_user, business_id)

    adjustment = (
        db.query(kitchen_models.KitchenInventoryAdjustment)
        .filter(
            kitchen_models.KitchenInventoryAdjustment.id == adjustment_id,
            kitchen_models.KitchenInventoryAdjustment.business_id == business_id
        )
        .first()
    )

    if not adjustment:
        raise HTTPException(status_code=404, detail="Adjustment not found")

    inventory = (
        db.query(kitchen_models.KitchenInventory)
        .filter(
            kitchen_models.KitchenInventory.kitchen_id == adjustment.kitchen_id,
            kitchen_models.KitchenInventory.item_id == adjustment.item_id,
            kitchen_models.KitchenInventory.business_id == business_id
        )
        .first()
    )

    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")

    old_qty = float(adjustment.quantity_adjusted)
    new_qty = float(data.quantity_adjusted)

    # 🔁 REVERT OLD
    inventory.quantity -= old_qty

    # 🔁 APPLY NEW
    new_inventory = inventory

    # validate stock
    if new_inventory.quantity + new_qty < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    new_inventory.quantity += new_qty

    # update adjustment
    adjustment.quantity_adjusted = new_qty
    adjustment.reason = data.reason
    adjustment.adjusted_by = current_user.username
    adjustment.adjusted_at = now_wat()

    db.commit()
    db.refresh(adjustment)

    return kitchen_schemas.KitchenInventoryAdjustmentDisplay(
        id=adjustment.id,
        kitchen_id=adjustment.kitchen_id,
        item=kitchen_schemas.KitchenItemMinimalDisplay(
            id=adjustment.item_id,
            name=inventory.item.name if inventory.item else ""
        ),
        quantity_adjusted=adjustment.quantity_adjusted,
        reason=adjustment.reason,
        adjusted_by=adjustment.adjusted_by,
        adjusted_at=adjustment.adjusted_at
    )


# -------------------------
# Delete kitchen adjustment (SIGN SAFE)
# -------------------------
@router.delete("/adjustments/{adjustment_id}")
def delete_kitchen_adjustment(
    adjustment_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    business_id = resolve_business_id(current_user, business_id)

    adjustment = (
        db.query(kitchen_models.KitchenInventoryAdjustment)
        .filter(
            kitchen_models.KitchenInventoryAdjustment.id == adjustment_id,
            kitchen_models.KitchenInventoryAdjustment.business_id == business_id
        )
        .first()
    )

    if not adjustment:
        raise HTTPException(status_code=404, detail="Adjustment not found")

    inventory = (
        db.query(kitchen_models.KitchenInventory)
        .filter(
            kitchen_models.KitchenInventory.kitchen_id == adjustment.kitchen_id,
            kitchen_models.KitchenInventory.item_id == adjustment.item_id,
            kitchen_models.KitchenInventory.business_id == business_id
        )
        .first()
    )

    if inventory:
        # 🔁 reverse signed adjustment
        inventory.quantity -= float(adjustment.quantity_adjusted)

    db.delete(adjustment)
    db.commit()

    return {
        "message": "Adjustment deleted successfully",
        "reversed_quantity": adjustment.quantity_adjusted,
        "current_stock": inventory.quantity if inventory else 0
    }





















