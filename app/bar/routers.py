from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import aliased
from typing import Optional, List
from sqlalchemy import and_
from datetime import datetime, date
from app.database import get_db
from app.users.auth import get_current_user
from app.users import schemas as user_schemas
from app.bar import models as bar_models, schemas as bar_schemas
from app.store import models as store_models
from app.bar.models import Bar, BarInventory, BarSale, BarSaleItem
from app.users.models import User
from app.users.permissions import role_required  # 👈 permission helper
from app.bar.models import Bar, BarInventoryReceipt
from typing import Optional
from datetime import timedelta
from app.barpayment import models as barpayment_models

from app.store.models import StoreItem
from app.bar.schemas import BarStockReceiveCreate, BarInventoryDisplay, BarItemSummarySchema, BarItemSummaryResponse
from datetime import datetime
from app.bar.schemas import  BarInventoryReceiptDisplay  # <- New response schema

from app.users.models import User
from app.bar.models import BarInventory, BarInventoryAdjustment
from app.bar.schemas import BarInventoryAdjustmentCreate, BarInventoryAdjustmentDisplay



from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.db import db_dependency
from app.core.business import resolve_business_id

from sqlalchemy.orm import selectinload

from app.core.timezone import now_wat, to_wat  # ✅ centralized WAT functions






router = APIRouter()



WAT = ZoneInfo("Africa/Lagos")  # Africa/Lagos timezone for consistent timestamps

def now_wat() -> datetime:
    """Return current time in Africa/Lagos as timezone-aware datetime"""
    return datetime.now(WAT)


# ----------------------------
# Create Bar
# ----------------------------
@router.post("/bars", response_model=bar_schemas.BarDisplay)
def create_bar(
    bar: bar_schemas.BarCreate,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["bar", "admin", "store"]))
):
    # Determine business scope
    if "super_admin" in current_user.roles:
        effective_business_id = business_id
        if not effective_business_id:
            raise HTTPException(status_code=400, detail="Super admin must provide business_id.")
    else:
        effective_business_id = current_user.business_id

    # Check for duplicate bar name within the same business
    existing = (
        db.query(bar_models.Bar)
        .filter_by(name=bar.name, business_id=effective_business_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Bar name already exists")

    # Create bar with business_id and timestamp
    new_bar = bar_models.Bar(
        **bar.dict(),
        business_id=effective_business_id,
        created_at=now_wat()
    )
    db.add(new_bar)
    db.commit()
    db.refresh(new_bar)
    return new_bar


# ----------------------------
# List Bars (full)
# ----------------------------
@router.get("/bars", response_model=List[bar_schemas.BarDisplay])
def list_bars(
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["bar", "admin" , "store"]))
):
    # Determine business scope
    if "super_admin" in current_user.roles:
        effective_business_id = business_id
        if not effective_business_id:
            raise HTTPException(status_code=400, detail="Super admin must provide business_id.")
    else:
        effective_business_id = current_user.business_id

    return (
        db.query(bar_models.Bar)
        .filter_by(business_id=effective_business_id)
        .order_by(bar_models.Bar.id.asc())
        .all()
    )


# ----------------------------
# List Bars (simple)
# ----------------------------
@router.get("/bars/simple", response_model=List[bar_schemas.BarDisplaySimple])
def list_bars_simple(
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["bar", "admin" , "store"]))
):
    # Determine business scope
    if "super_admin" in current_user.roles:
        effective_business_id = business_id
        if not effective_business_id:
            raise HTTPException(status_code=400, detail="Super admin must provide business_id.")
    else:
        effective_business_id = current_user.business_id

    return (
        db.query(bar_models.Bar)
        .filter_by(business_id=effective_business_id)
        .order_by(bar_models.Bar.id.asc())
        .all()
    )



# ----------------------------
# BAR INVENTORY (Multi-Tenant)
# ----------------------------


# ----------------------------
# Update Bar
# ----------------------------
@router.put("/bars/{bar_id}", response_model=bar_schemas.BarDisplay)
def update_bar(
    bar_id: int,
    bar_update: bar_schemas.BarCreate,
    business_id: Optional[int] = Query(None, description="Required for super admin"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["bar", "super_admin"]))
):
    # For super admin, ensure business_id is provided
    if "super_admin" in current_user.roles and not business_id:
        raise HTTPException(status_code=400, detail="Super admin must provide business_id")

    resolved_business_id = resolve_business_id(current_user, business_id)

    bar = db.query(bar_models.Bar).filter_by(id=bar_id, business_id=resolved_business_id).first()
    if not bar:
        raise HTTPException(status_code=404, detail="Bar not found")

    # Ensure unique bar name within the business
    existing = db.query(bar_models.Bar).filter(
        bar_models.Bar.name == bar_update.name,
        bar_models.Bar.id != bar_id,
        bar_models.Bar.business_id == resolved_business_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bar name already exists for this business")

    for field, value in bar_update.dict().items():
        setattr(bar, field, value)

    db.commit()
    db.refresh(bar)
    return bar


# ----------------------------
# Delete Bar (Multi-Tenant)
# ----------------------------
@router.delete("/{bar_id}")
def delete_bar(
    bar_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (NEW STANDARD)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch bar (tenant-safe)
        # ------------------------------
        bar = (
            db.query(bar_models.Bar)
            .filter(
                bar_models.Bar.id == bar_id,
                bar_models.Bar.business_id == business_id
            )
            .first()
        )

        if not bar:
            raise HTTPException(status_code=404, detail="Bar not found")

        # ------------------------------
        # 3️⃣ Delete bar
        # ------------------------------
        db.delete(bar)
        db.commit()

        return {
            "message": "Bar deleted successfully",
            "bar_id": bar_id,
            "business_id": business_id
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete bar: {str(e)}"
        )


@router.get("/items/simple-search", response_model=List[bar_schemas.BarSaleItemSummary])
def search_bar_items(
    search: str = Query("", description="Search term for item name"),
    limit: int = Query(50, description="Maximum number of results"),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id"
    ),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "store", "admin", "super_admin"])
    ),
):
    """
    Search bar items by name with latest selling price.
    Multi-tenant secured.
    """

    # ✅ Resolve tenant (STRICT)
    resolved_business_id = resolve_business_id(current_user, business_id)

    # 🔁 Subquery: latest inventory per item (PER BUSINESS)
    subquery = (
        db.query(
            bar_models.BarInventory.item_id,
            func.max(bar_models.BarInventory.id).label("latest_inventory_id")
        )
        .filter(bar_models.BarInventory.business_id == resolved_business_id)  # 🔒 CRITICAL
        .group_by(bar_models.BarInventory.item_id)
        .subquery()
    )

    # 🔗 Main query (STRICT tenant filtering)
    query = (
        db.query(
            store_models.StoreItem.id.label("item_id"),
            store_models.StoreItem.name.label("item_name"),
            store_models.StoreItem.item_type.label("item_type"),
            bar_models.BarInventory.selling_price.label("selling_price"),
        )
        .outerjoin(subquery, subquery.c.item_id == store_models.StoreItem.id)
        .outerjoin(
            bar_models.BarInventory,
            bar_models.BarInventory.id == subquery.c.latest_inventory_id
        )
        .filter(
            store_models.StoreItem.item_type == "bar",
            store_models.StoreItem.business_id == resolved_business_id  # 🔒 CRITICAL
        )
    )

    # 🔍 Search filter
    if search:
        query = query.filter(
            store_models.StoreItem.name.ilike(f"%{search}%")
        )

    # ⚡ Safe limit (prevent abuse)
    items = query.order_by(store_models.StoreItem.name.asc()).limit(min(limit, 100)).all()

    # 🧾 Map to schema
    return [
        bar_schemas.BarSaleItemSummary(
            item_id=item.item_id,
            item_name=item.item_name,
            selling_price=item.selling_price or 0,
            quantity=0,
            total_amount=0
        )
        for item in items
    ]


# ----------------------------
# Get Bar Items (Simple) - Multi-Tenant
# ----------------------------
@router.get("/items/simple", response_model=List[bar_schemas.BarSaleItemSummary])
def get_bar_items(
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (NEW STANDARD)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Subquery (latest inventory)
        # ------------------------------
        subquery = (
            db.query(
                bar_models.BarInventory.item_id,
                func.max(bar_models.BarInventory.id).label("latest_inventory_id")
            )
            .filter(
                bar_models.BarInventory.business_id == business_id
            )
            .group_by(bar_models.BarInventory.item_id)
            .subquery()
        )

        # ------------------------------
        # 3️⃣ Get items (tenant-safe)
        # ------------------------------
        items = (
            db.query(
                store_models.StoreItem.id.label("item_id"),
                store_models.StoreItem.name.label("item_name"),
                store_models.StoreItem.item_type.label("item_type"),
                bar_models.BarInventory.selling_price.label("selling_price"),
            )
            .outerjoin(subquery, subquery.c.item_id == store_models.StoreItem.id)
            .outerjoin(
                bar_models.BarInventory,
                bar_models.BarInventory.id == subquery.c.latest_inventory_id
            )
            .filter(
                store_models.StoreItem.item_type == "bar",
                store_models.StoreItem.business_id == business_id
            )
            .all()
        )

        # ------------------------------
        # 4️⃣ Response
        # ------------------------------
        return [
            bar_schemas.BarSaleItemSummary(
                item_id=item.item_id,
                item_name=item.item_name,
                selling_price=item.selling_price or 0,
                quantity=0,
                total_amount=0
            )
            for item in items
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch bar items: {str(e)}"
        )



# ----------------------------
# Get Bar Items (Simple Sell Price) - Multi-Tenant
# ----------------------------
@router.get("/items/simplesellprice", response_model=List[bar_schemas.BarSaleItemSummary])
def get_bar_items(
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin" , "store"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Get latest bar inventory price per item
        # ------------------------------
        subquery = (
            db.query(
                bar_models.BarInventory.item_id,
                func.max(bar_models.BarInventory.id).label("latest_id")
            )
            .filter(bar_models.BarInventory.business_id == business_id)
            .group_by(bar_models.BarInventory.item_id)
            .subquery()
        )

        # ------------------------------
        # 3️⃣ Join StoreItem + latest BarInventory price
        # ------------------------------
        items = (
            db.query(
                store_models.StoreItem.id.label("item_id"),
                store_models.StoreItem.name.label("item_name"),
                store_models.StoreItem.item_type.label("item_type"),
                bar_models.BarInventory.selling_price.label("selling_price"),
            )
            .join(subquery, subquery.c.item_id == store_models.StoreItem.id)
            .join(
                bar_models.BarInventory,
                bar_models.BarInventory.id == subquery.c.latest_id
            )
            .filter(
                store_models.StoreItem.item_type == "bar",
                store_models.StoreItem.business_id == business_id
            )
            .all()
        )

        # ------------------------------
        # 4️⃣ Response (NOW SHOWS UPDATED PRICE)
        # ------------------------------
        return [
            bar_schemas.BarSaleItemSummary(
                item_id=item.item_id,
                item_name=item.item_name,
                selling_price=float(item.selling_price or 0),
                quantity=0,
                total_amount=0
            )
            for item in items
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch bar items (sell price): {str(e)}"
        )



# ----------------------------
# Update Bar Item Selling Price (Multi-Tenant SAFE)
# ----------------------------
@router.put("/inventory/set-price", response_model=bar_schemas.BarInventoryDisplay)
def update_selling_price(
    data: bar_schemas.BarPriceUpdate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin" , "store"])
    )
):
    try:
        # 1️⃣ Resolve business
        business_id = resolve_business_id(current_user, business_id)

        # 2️⃣ VALIDATE BAR (🔥 FIX FOR YOUR ERROR)
        bar = (
            db.query(bar_models.Bar)
            .filter(
                bar_models.Bar.id == data.bar_id,
                bar_models.Bar.business_id == business_id
            )
            .first()
        )

        if not bar:
            raise HTTPException(
                status_code=404,
                detail="Bar not found in this business"
            )

        # 3️⃣ Find inventory record
        bar_item = (
            db.query(bar_models.BarInventory)
            .filter(
                bar_models.BarInventory.bar_id == data.bar_id,
                bar_models.BarInventory.item_id == data.item_id,
                bar_models.BarInventory.business_id == business_id
            )
            .first()
        )

        if bar_item:
            bar_item.selling_price = data.new_price
        else:
            bar_item = bar_models.BarInventory(
                bar_id=data.bar_id,
                item_id=data.item_id,
                selling_price=data.new_price,
                quantity=0,
                business_id=business_id
            )
            db.add(bar_item)

        db.commit()
        db.refresh(bar_item)

        # 4️⃣ Fetch item (tenant safe)
        item = (
            db.query(store_models.StoreItem)
            .filter(
                store_models.StoreItem.id == bar_item.item_id,
                store_models.StoreItem.business_id == business_id
            )
            .first()
        )

        return {
            "id": bar_item.id,
            "item_id": bar_item.item_id,
            "item_name": item.name if item else None,
            "bar_id": bar_item.bar_id,
            "bar_name": bar.name,
            "quantity": bar_item.quantity,
            "selling_price": bar_item.selling_price,
            "received_at": bar_item.received_at,
            "note": bar_item.note
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update selling price: {str(e)}"
        )



# ----------------------------
# BAR SALES
# ----------------------------

from app.store import models as store_models   # 👈 add this import
from datetime import datetime, timezone


# ----------------------------
# Create Bar Sale (Multi-Tenant Safe)
# ----------------------------
@router.post("/sales", response_model=bar_schemas.BarSaleDisplay)
def create_bar_sale(
    sale_data: bar_schemas.BarSaleCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # -------------------------------------------------
        # 1️⃣ Resolve business
        # -------------------------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -------------------------------------------------
        # 2️⃣ Validate BAR (TENANT SAFE)
        # -------------------------------------------------
        bar = db.query(bar_models.Bar).filter(
            bar_models.Bar.id == sale_data.bar_id,
            bar_models.Bar.business_id == business_id
        ).first()

        if not bar:
            raise HTTPException(status_code=404, detail="Bar not found")

        # -------------------------------------------------
        # 3️⃣ Validate sale date
        # -------------------------------------------------
        sale_date = sale_data.sale_date

        if sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)

        if sale_date > now_utc:
            raise HTTPException(
                status_code=400,
                detail="Sale date cannot be in the future."
            )

        # -------------------------------------------------
        # 4️⃣ Create Sale
        # -------------------------------------------------
        sale = bar_models.BarSale(
            bar_id=sale_data.bar_id,
            sale_date=sale_date,
            created_by_id=current_user.id,
            status="unpaid",
            business_id=business_id  # ✅ IMPORTANT
        )

        db.add(sale)
        db.flush()

        sale_items_response = []
        total_amount = 0.0

        # -------------------------------------------------
        # 5️⃣ Process Items
        # -------------------------------------------------
        for item_data in sale_data.items:

            # 🔹 Get inventory (tenant safe)
            inventory = db.query(bar_models.BarInventory).filter(
                bar_models.BarInventory.bar_id == sale_data.bar_id,
                bar_models.BarInventory.item_id == item_data.item_id,
                bar_models.BarInventory.business_id == business_id
            ).first()

            if not inventory:
                raise HTTPException(
                    status_code=400,
                    detail=f"Item ID {item_data.item_id} not found in bar inventory."
                )

            # 🔹 Get store item (tenant safe)
            store_item = db.query(store_models.StoreItem).filter(
                store_models.StoreItem.id == item_data.item_id,
                store_models.StoreItem.business_id == business_id
            ).first()

            if not store_item or store_item.item_type != "bar":
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid bar item: {item_data.item_id}"
                )

            # -------------------------------------------------
            # 6️⃣ Validate stock
            # -------------------------------------------------
            if inventory.quantity < item_data.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for {store_item.name}"
                )

            # -------------------------------------------------
            # 7️⃣ Selling price validation
            # -------------------------------------------------
            if not item_data.selling_price or item_data.selling_price <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Selling price required for {store_item.name}"
                )

            selling_price = item_data.selling_price

            # Optional: sync catalog price
            if not store_item.selling_price:
                store_item.selling_price = selling_price

            # -------------------------------------------------
            # 8️⃣ Deduct stock
            # -------------------------------------------------
            inventory.quantity -= item_data.quantity

            # -------------------------------------------------
            # 9️⃣ Calculate totals
            # -------------------------------------------------
            item_total = selling_price * item_data.quantity
            total_amount += item_total

            # -------------------------------------------------
            # 🔟 Save sale item
            # -------------------------------------------------
            sale_item = bar_models.BarSaleItem(
                sale_id=sale.id,
                bar_inventory_id=inventory.id,
                quantity=item_data.quantity,
                selling_price=selling_price,
                total_amount=item_total,
                business_id=business_id  # ✅ IMPORTANT
            )

            db.add(sale_item)

            sale_items_response.append(
                bar_schemas.BarSaleItemSummary(
                    item_id=store_item.id,
                    item_name=store_item.name,
                    quantity=item_data.quantity,
                    selling_price=selling_price,
                    total_amount=item_total
                )
            )

        # -------------------------------------------------
        # 11️⃣ Finalize sale
        # -------------------------------------------------
        sale.total_amount = total_amount

        db.commit()
        db.refresh(sale)

        # -------------------------------------------------
        # 12️⃣ Response
        # -------------------------------------------------
        return bar_schemas.BarSaleDisplay(
            id=sale.id,
            sale_date=sale.sale_date,
            bar_id=sale.bar_id,
            bar_name=bar.name,
            created_by=current_user.username,
            status=sale.status,
            total_amount=total_amount,
            sale_items=sale_items_response
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create bar sale: {str(e)}"
        )


# ----------------------------
# List Bar Sales (Multi-Tenant Safe)
# ----------------------------
@router.get("/sales", response_model=bar_schemas.BarSaleListResponse)
def list_bar_sales(
    bar_id: Optional[int] = None,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # -------------------------------------------------
        # 1️⃣ Resolve business
        # -------------------------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -------------------------------------------------
        # 2️⃣ Base Query (TENANT SAFE + EAGER LOAD)
        # -------------------------------------------------
        query = db.query(bar_models.BarSale).options(
            joinedload(bar_models.BarSale.bar),
            joinedload(bar_models.BarSale.created_by_user),
            joinedload(bar_models.BarSale.sale_items)
                .joinedload(bar_models.BarSaleItem.bar_inventory)
                .joinedload(bar_models.BarInventory.item)
        ).filter(
            bar_models.BarSale.business_id == business_id  # ✅ IMPORTANT
        )

        # -------------------------------------------------
        # 3️⃣ Filters (UNCHANGED LOGIC)
        # -------------------------------------------------
        if bar_id:
            query = query.filter(bar_models.BarSale.bar_id == bar_id)

        if start_date and end_date:
            query = query.filter(
                func.date(bar_models.BarSale.sale_date).between(start_date, end_date)
            )
        elif start_date:
            query = query.filter(
                func.date(bar_models.BarSale.sale_date) >= start_date
            )
        elif end_date:
            query = query.filter(
                func.date(bar_models.BarSale.sale_date) <= end_date
            )

        # -------------------------------------------------
        # 4️⃣ Order
        # -------------------------------------------------
        sales = query.order_by(
            bar_models.BarSale.sale_date.desc()
        ).all()

        # -------------------------------------------------
        # 5️⃣ Build Response
        # -------------------------------------------------
        results = []
        total_sales_amount = 0.0

        for sale in sales:

            # skip dirty data safety
            if not sale.bar_id:
                continue

            sale_items = []
            sale_total = 0.0

            for s_item in sale.sale_items:

                inv = s_item.bar_inventory
                store_item = inv.item if inv else None

                if not inv or not store_item:
                    continue

                # 🔒 tenant safety
                if store_item.business_id != business_id:
                    continue

                item_name = store_item.name
                item_id = inv.item_id

                selling_price = float(s_item.selling_price or 0.0)
                total_amount = float(s_item.total_amount or 0.0)

                sale_items.append({
                    "item_id": item_id,
                    "item_name": item_name,
                    "quantity": int(s_item.quantity or 0),
                    "selling_price": selling_price,
                    "total_amount": total_amount,
                })

                sale_total += total_amount

            results.append({
                "id": sale.id,
                "sale_date": sale.sale_date,
                "bar_id": sale.bar_id,
                "bar_name": sale.bar.name if sale.bar else "",
                "created_by": sale.created_by_user.username if sale.created_by_user else "",
                "status": sale.status,
                "total_amount": sale_total,
                "sale_items": sale_items,
            })

            total_sales_amount += sale_total

        # -------------------------------------------------
        # 6️⃣ Final Response
        # -------------------------------------------------
        return {
            "total_entries": len(results),
            "total_sales_amount": total_sales_amount,
            "sales": results,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list bar sales: {str(e)}"
        )



# ----------------------------
# Bar Item Summary (Multi-Tenant Safe)
# ----------------------------
@router.get("/item-summary", response_model=dict)
def get_bar_item_summary(
    bar_id: Optional[int] = Query(None, description="Filter by Bar ID"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # -------------------------------------------------
        # 1️⃣ Resolve business
        # -------------------------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -------------------------------------------------
        # 2️⃣ Validate date range
        # -------------------------------------------------
        if start_date and end_date and start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be after end date"
            )

        # -------------------------------------------------
        # 3️⃣ Base query (TENANT SAFE)
        # -------------------------------------------------
        sales_query = db.query(bar_models.BarSale).filter(
            bar_models.BarSale.business_id == business_id
        )

        if bar_id:
            sales_query = sales_query.filter(bar_models.BarSale.bar_id == bar_id)

        if start_date:
            sales_query = sales_query.filter(
                func.date(bar_models.BarSale.sale_date) >= start_date
            )

        if end_date:
            sales_query = sales_query.filter(
                func.date(bar_models.BarSale.sale_date) <= end_date
            )

        sales = sales_query.all()

        # -------------------------------------------------
        # 4️⃣ Item summary
        # -------------------------------------------------
        item_summary = {}
        grand_total = 0.0

        payment_summary = {
            "total_sales": 0.0,
            "total_paid": 0.0,
            "total_due": 0.0,
            "total_cash": 0.0,
            "total_pos": 0.0,
            "total_transfer": 0.0,
            "banks": {}
        }

        # -------------------------------------------------
        # 5️⃣ Loop sales
        # -------------------------------------------------
        for sale in sales:

            if sale.business_id != business_id:
                continue

            sale_total = float(sale.total_amount or 0)

            # ================= ITEMS =================
            for sale_item in sale.sale_items:

                inv = sale_item.bar_inventory
                store_item = inv.item if inv else None

                if not inv or not store_item:
                    continue

                # tenant safety
                if store_item.business_id != business_id:
                    continue

                name = store_item.name
                price = float(sale_item.selling_price or 0)
                qty = int(sale_item.quantity or 0)
                amount = float(sale_item.total_amount or (qty * price))

                key = f"{name}_{price}"

                if key not in item_summary:
                    item_summary[key] = {
                        "item": name,
                        "qty": 0,
                        "price": price,
                        "amount": 0
                    }

                item_summary[key]["qty"] += qty
                item_summary[key]["amount"] += amount

                grand_total += amount

            # ================= PAYMENTS =================
            total_paid_for_sale = 0.0

            for payment in sale.payments:

                if payment.status != "active":
                    continue

                # tenant safety (if payments table has business_id)
                if hasattr(payment, "business_id") and payment.business_id != business_id:
                    continue

                amount_paid = float(payment.amount_paid or 0)
                total_paid_for_sale += amount_paid

                mode = (payment.payment_method or "").upper()

                if mode == "CASH":
                    payment_summary["total_cash"] += amount_paid
                elif mode == "POS":
                    payment_summary["total_pos"] += amount_paid
                elif mode == "TRANSFER":
                    payment_summary["total_transfer"] += amount_paid

                bank = (payment.bank or "").upper().strip()
                if bank:
                    if bank not in payment_summary["banks"]:
                        payment_summary["banks"][bank] = {
                            "pos": 0.0,
                            "transfer": 0.0
                        }

                    if mode == "POS":
                        payment_summary["banks"][bank]["pos"] += amount_paid
                    elif mode == "TRANSFER":
                        payment_summary["banks"][bank]["transfer"] += amount_paid

            # ================= TOTALS =================
            payment_summary["total_sales"] += sale_total
            payment_summary["total_paid"] += total_paid_for_sale
            payment_summary["total_due"] += sale_total - total_paid_for_sale

        # -------------------------------------------------
        # 6️⃣ RESPONSE
        # -------------------------------------------------
        items = list(item_summary.values())

        return {
            "items": items,
            "items_summary": {
                "grand_total": float(grand_total),
                "total_items": len(items)
            },
            "payment_summary": payment_summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    


@router.get("/unpaid_sales", response_model=dict)
def list_unpaid_sales(
    bar_id: Optional[int] = None,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Base query (tenant-safe + eager loading)
        # ------------------------------
        query = (
            db.query(bar_models.BarSale)
            .options(
                joinedload(bar_models.BarSale.bar),
                joinedload(bar_models.BarSale.created_by_user),
                joinedload(bar_models.BarSale.sale_items)
                    .joinedload(bar_models.BarSaleItem.bar_inventory)
                    .joinedload(bar_models.BarInventory.item)
            )
            .filter(bar_models.BarSale.business_id == business_id)
        )

        # ------------------------------
        # 3️⃣ Filters
        # ------------------------------
        if bar_id:
            query = query.filter(bar_models.BarSale.bar_id == bar_id)

        if start_date and end_date:
            query = query.filter(
                func.date(bar_models.BarSale.sale_date).between(start_date, end_date)
            )
        elif start_date:
            query = query.filter(func.date(bar_models.BarSale.sale_date) >= start_date)
        elif end_date:
            query = query.filter(func.date(bar_models.BarSale.sale_date) <= end_date)

        query = query.order_by(bar_models.BarSale.sale_date.desc())
        sales = query.all()

        # ------------------------------
        # 4️⃣ Build response
        # ------------------------------
        results = []
        total_due_all = 0.0

        for sale in sales:

            # 🔹 tenant-safe payment sum
            total_paid = (
                db.query(func.coalesce(func.sum(barpayment_models.BarPayment.amount_paid), 0))
                .filter(
                    barpayment_models.BarPayment.bar_sale_id == sale.id,
                    barpayment_models.BarPayment.status == "active",
                    barpayment_models.BarPayment.business_id == business_id
                )
                .scalar()
            )

            total_amount = float(sale.total_amount or 0)
            balance = total_amount - float(total_paid or 0)

            if balance <= 0:
                continue

            status = "unpaid" if total_paid == 0 else "part payment"

            results.append({
                "bar_sale_id": sale.id,
                "sale_date": sale.sale_date.isoformat() if sale.sale_date else None,
                "sale_amount": total_amount,
                "amount_paid": float(total_paid or 0),
                "balance_due": balance,
                "status": status,
                "bar_name": sale.bar.name if sale.bar else "",
                "bar_id": sale.bar_id
            })

            total_due_all += balance

        # ------------------------------
        # 5️⃣ Final response
        # ------------------------------
        return {
            "business_id": business_id,
            "total_entries": len(results),
            "total_due": total_due_all,
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch unpaid sales: {str(e)}"
        )


from sqlalchemy import func
from sqlalchemy.orm import joinedload

@router.put("/sales/{sale_id}", response_model=bar_schemas.BarSaleDisplay)
def update_bar_sale(
    sale_id: int,
    sale_data: bar_schemas.BarSaleCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (tenant-safe)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch sale (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .filter(
                bar_models.BarSale.id == sale_id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")

        if sale.bar_id != sale_data.bar_id:
            raise HTTPException(status_code=400, detail="Bar ID mismatch")

        # ------------------------------
        # 3️⃣ Update sale date
        # ------------------------------
        sale.sale_date = sale_data.sale_date or sale.sale_date

        # ------------------------------
        # 4️⃣ Existing + requested items
        # ------------------------------
        existing_items = {
            si.bar_inventory.item_id: si for si in sale.sale_items
        }

        requested_items = {}
        for it in sale_data.items:
            if not it.item_id:
                raise HTTPException(status_code=400, detail="Every item must have item_id")

            requested_items[it.item_id] = {
                "quantity": int(it.quantity or 0),
                "selling_price": float(it.selling_price or 0.0)
            }

        all_item_ids = set(existing_items.keys()) | set(requested_items.keys())

        # ------------------------------
        # 5️⃣ Lock inventories (tenant-safe)
        # ------------------------------
        inventories = {}

        for iid in all_item_ids:
            inv = (
                db.query(bar_models.BarInventory)
                .filter(
                    bar_models.BarInventory.bar_id == sale.bar_id,
                    bar_models.BarInventory.item_id == iid,
                    bar_models.BarInventory.business_id == business_id
                )
                .with_for_update()
                .first()
            )

            if not inv:
                raise HTTPException(
                    status_code=404,
                    detail=f"Item {iid} not found in this bar"
                )

            inventories[iid] = inv

        # ------------------------------
        # 6️⃣ Apply stock + rebuild items
        # ------------------------------
        for iid in all_item_ids:
            inv = inventories[iid]

            original_qty = (
                existing_items[iid].quantity if iid in existing_items else 0
            )

            requested_qty = (
                requested_items[iid]["quantity"] if iid in requested_items else 0
            )

            price = (
                requested_items[iid]["selling_price"]
                if iid in requested_items else 0.0
            )

            # 🔹 restore old stock, then deduct new
            inv.quantity = (inv.quantity + original_qty) - requested_qty

            # 🔹 delete old item line
            if iid in existing_items:
                db.delete(existing_items[iid])

            # 🔹 add updated item line ✅ FIXED POSITION
            if requested_qty > 0:
                db.add(
                    bar_models.BarSaleItem(
                        sale_id=sale.id,
                        bar_inventory_id=inv.id,
                        quantity=requested_qty,
                        selling_price=price,
                        total_amount=price * requested_qty,
                        business_id=business_id
                    )
                )

        db.flush()

        # ------------------------------
        # 7️⃣ Recalculate total
        # ------------------------------
        sale.total_amount = (
            db.query(func.coalesce(func.sum(bar_models.BarSaleItem.total_amount), 0))
            .filter(bar_models.BarSaleItem.sale_id == sale.id)
            .scalar()
        )

        db.commit()
        db.refresh(sale)

        # ------------------------------
        # 8️⃣ Reload (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .options(
                joinedload(bar_models.BarSale.bar),
                joinedload(bar_models.BarSale.created_by_user),
                joinedload(bar_models.BarSale.sale_items)
                    .joinedload(bar_models.BarSaleItem.bar_inventory)
                    .joinedload(bar_models.BarInventory.item)
            )
            .filter(
                bar_models.BarSale.id == sale.id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        # ------------------------------
        # 9️⃣ Response build
        # ------------------------------
        sale_items = [
            bar_schemas.BarSaleItemSummary(
                item_id=item.bar_inventory.item_id,
                item_name=item.bar_inventory.item.name,
                quantity=item.quantity,
                selling_price=item.selling_price,
                total_amount=item.total_amount
            )
            for item in sale.sale_items
        ]

        return bar_schemas.BarSaleDisplay(
            id=sale.id,
            sale_date=sale.sale_date,
            bar_id=sale.bar_id,
            bar_name=sale.bar.name if sale.bar else "",
            created_by=sale.created_by_user.username if sale.created_by_user else "",
            status=sale.status,
            total_amount=sale.total_amount,
            sale_items=sale_items
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sales/{sale_id}")
def delete_bar_sale(
    sale_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch sale (tenant-safe)
        # ------------------------------
        sale = (
            db.query(bar_models.BarSale)
            .filter(
                bar_models.BarSale.id == sale_id,
                bar_models.BarSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")

        # ------------------------------
        # 3️⃣ Restore inventory (important fix)
        # ------------------------------
        for item in sale.sale_items:
            inv = (
                db.query(bar_models.BarInventory)
                .filter(
                    bar_models.BarInventory.id == item.bar_inventory_id,
                    bar_models.BarInventory.business_id == business_id
                )
                .first()
            )

            if inv:
                inv.quantity += item.quantity

        # ------------------------------
        # 4️⃣ Delete sale (cascade handles items)
        # ------------------------------
        db.delete(sale)
        db.commit()

        return {
            "message": "Bar sale deleted successfully",
            "sale_id": sale_id,
            "business_id": business_id
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete sale: {str(e)}"
        )







@router.get("/stock-balance", response_model=List[bar_schemas.BarStockBalance])
def get_bar_stock_balance(
    item_id: Optional[int] = Query(None, description="Filter by specific item"),
    bar_id: Optional[int] = Query(None, description="Filter by bar"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    search: Optional[str] = Query(None, description="Search by item name or category"),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["store", "bar", "admin", "super_admin"]))
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # =============================================================
        # 1️⃣ TOTAL RECEIVED (Store → Bar)
        # =============================================================
        received_query = (
            db.query(
                store_models.StoreIssueItem.item_id,
                store_models.StoreIssue.bar_id.label("bar_id"),
                func.sum(store_models.StoreIssueItem.quantity).label("total_received")
            )
            .join(store_models.StoreIssue)
            .filter(
                store_models.StoreIssue.issue_to == "bar",
                store_models.StoreIssue.business_id == business_id  # ✅ added
            )
        )

        if item_id:
            received_query = received_query.filter(store_models.StoreIssueItem.item_id == item_id)
        if bar_id:
            received_query = received_query.filter(store_models.StoreIssue.bar_id == bar_id)
        if start_date:
            received_query = received_query.filter(store_models.StoreIssue.issue_date >= start_date)
        if end_date:
            received_query = received_query.filter(store_models.StoreIssue.issue_date <= end_date)

        received_query = received_query.group_by(
            store_models.StoreIssueItem.item_id,
            store_models.StoreIssue.bar_id
        )

        received_data = {
            (row.item_id, row.bar_id): float(row.total_received or 0)
            for row in received_query.all()
        }

        # =============================================================
        # 2️⃣ TOTAL SOLD (Bar Sales)
        # =============================================================
        sold_query = (
            db.query(
                bar_models.BarInventory.item_id,
                bar_models.BarSale.bar_id,
                func.sum(bar_models.BarSaleItem.quantity).label("total_sold")
            )
            .join(bar_models.BarSaleItem.bar_inventory)
            .join(bar_models.BarSaleItem.sale)
            .filter(
                bar_models.BarSale.business_id == business_id  # ✅ added
            )
        )

        if item_id:
            sold_query = sold_query.filter(bar_models.BarInventory.item_id == item_id)
        if bar_id:
            sold_query = sold_query.filter(bar_models.BarSale.bar_id == bar_id)
        if start_date:
            sold_query = sold_query.filter(bar_models.BarSale.sale_date >= start_date)
        if end_date:
            sold_query = sold_query.filter(bar_models.BarSale.sale_date <= end_date)

        sold_query = sold_query.group_by(
            bar_models.BarInventory.item_id,
            bar_models.BarSale.bar_id
        )

        sold_data = {
            (row.item_id, row.bar_id): float(row.total_sold or 0)
            for row in sold_query.all()
        }

        # =============================================================
        # 3️⃣ TOTAL ADJUSTED (Inventory Adjustments)
        # =============================================================
        adjusted_query = (
            db.query(
                bar_models.BarInventoryAdjustment.item_id,
                bar_models.BarInventoryAdjustment.bar_id,
                func.sum(bar_models.BarInventoryAdjustment.quantity_adjusted).label("total_adjusted")
            )
            .filter(
                bar_models.BarInventoryAdjustment.business_id == business_id  # ✅ added
            )
        )

        if item_id:
            adjusted_query = adjusted_query.filter(bar_models.BarInventoryAdjustment.item_id == item_id)
        if bar_id:
            adjusted_query = adjusted_query.filter(bar_models.BarInventoryAdjustment.bar_id == bar_id)
        if start_date:
            adjusted_query = adjusted_query.filter(bar_models.BarInventoryAdjustment.adjusted_at >= start_date)
        if end_date:
            adjusted_query = adjusted_query.filter(bar_models.BarInventoryAdjustment.adjusted_at <= end_date)

        adjusted_query = adjusted_query.group_by(
            bar_models.BarInventoryAdjustment.item_id,
            bar_models.BarInventoryAdjustment.bar_id
        )

        adjusted_data = {
            (row.item_id, row.bar_id): float(row.total_adjusted or 0)
            for row in adjusted_query.all()
        }

        # =============================================================
        # 4️⃣ MERGE + CALCULATE
        # =============================================================
        all_keys = set(received_data.keys()) | set(sold_data.keys()) | set(adjusted_data.keys())
        results = []

        for (i_id, b_id) in all_keys:
            if b_id is None:
                continue

            total_received = received_data.get((i_id, b_id), 0)
            total_sold = sold_data.get((i_id, b_id), 0)
            total_adjusted = adjusted_data.get((i_id, b_id), 0)

            balance = total_received - total_sold - total_adjusted

            # ✅ tenant-safe item
            item = db.query(store_models.StoreItem).filter_by(
                id=i_id,
                business_id=business_id
            ).first()

            if not item or item.item_type != "bar":
                continue

            # ✅ tenant-safe bar
            bar = db.query(bar_models.Bar).filter_by(
                id=b_id,
                business_id=business_id
            ).first()

            # Search filter (unchanged)
            if search:
                search_lower = search.lower()
                if search_lower not in item.name.lower() and (
                    not item.category or search_lower not in item.category.name.lower()
                ):
                    continue

            # Latest unit price (tenant-safe)
            latest_stock = (
                db.query(store_models.StoreStockEntry)
                .filter(
                    store_models.StoreStockEntry.item_id == i_id,
                    store_models.StoreStockEntry.business_id == business_id
                )
                .order_by(
                    store_models.StoreStockEntry.purchase_date.desc(),
                    store_models.StoreStockEntry.id.desc()
                )
                .first()
            )

            unit_price = float(latest_stock.unit_price) if latest_stock and latest_stock.unit_price else None
            balance_total_amount = round(balance * unit_price, 2) if unit_price else None

            results.append(
                bar_schemas.BarStockBalance(
                    bar_id=b_id,
                    bar_name=bar.name if bar else "Unknown",
                    item_id=i_id,
                    item_name=item.name,
                    category_name=item.category.name if item.category else "Uncategorized",
                    item_type=item.item_type,
                    unit=item.unit,
                    total_received=total_received,
                    total_sold=total_sold,
                    total_adjusted=total_adjusted,
                    balance=balance,
                    last_unit_price=unit_price,
                    balance_total_amount=balance_total_amount,
                )
            )

        results.sort(key=lambda x: (x.bar_name.lower(), x.item_name.lower()))
        return results

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve bar stock balance: {str(e)}"
        )


    


@router.post("/adjust", response_model=BarInventoryAdjustmentDisplay)
def adjust_bar_inventory(
    adjustment_data: BarInventoryAdjustmentCreate,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        bar_id = adjustment_data.bar_id
        item_id = adjustment_data.item_id

        # ------------------------------
        # 2️⃣ Validate bar (tenant-safe)
        # ------------------------------
        bar = db.query(bar_models.Bar).filter(
            bar_models.Bar.id == bar_id,
            bar_models.Bar.business_id == business_id
        ).first()

        if not bar:
            raise HTTPException(status_code=404, detail="Bar not found")

        # ------------------------------
        # 3️⃣ Validate item (tenant-safe)
        # ------------------------------
        item = db.query(store_models.StoreItem).filter(
            store_models.StoreItem.id == item_id,
            store_models.StoreItem.business_id == business_id
        ).first()

        if not item or item.item_type != "bar":
            raise HTTPException(status_code=404, detail="Bar item not found")

        # ------------------------------
        # 🔢 STEP 1: TOTAL ISSUED
        # ------------------------------
        issued = (
            db.query(func.coalesce(func.sum(store_models.StoreIssueItem.quantity), 0))
            .join(store_models.StoreIssue)
            .filter(
                store_models.StoreIssue.bar_id == bar_id,
                store_models.StoreIssue.issue_to == "bar",
                store_models.StoreIssue.business_id == business_id,
                store_models.StoreIssueItem.item_id == item_id
            )
            .scalar()
        )

        # ------------------------------
        # 🔢 STEP 2: TOTAL SOLD
        # ------------------------------
        sold = (
            db.query(func.coalesce(func.sum(bar_models.BarSaleItem.quantity), 0))
            .join(bar_models.BarSaleItem.bar_inventory)
            .join(bar_models.BarSaleItem.sale)
            .filter(
                bar_models.BarSale.bar_id == bar_id,
                bar_models.BarSale.business_id == business_id,
                bar_models.BarInventory.item_id == item_id
            )
            .scalar()
        )

        # ------------------------------
        # 🔢 STEP 3: TOTAL ADJUSTED
        # ------------------------------
        adjusted = (
            db.query(func.coalesce(func.sum(bar_models.BarInventoryAdjustment.quantity_adjusted), 0))
            .filter(
                bar_models.BarInventoryAdjustment.bar_id == bar_id,
                bar_models.BarInventoryAdjustment.item_id == item_id,
                bar_models.BarInventoryAdjustment.business_id == business_id
            )
            .scalar()
        )

        # ------------------------------
        # 🧮 STEP 4: COMPUTE BALANCE
        # ------------------------------
        balance = issued - sold - adjusted

        # ------------------------------
        # ❗ VALIDATION
        # ------------------------------
        if adjustment_data.quantity_adjusted > balance:
            raise HTTPException(
                status_code=400,
                detail=f"Adjustment exceeds available stock. Available: {balance}"
            )

        # ------------------------------
        # 📦 STEP 5: SAVE ADJUSTMENT
        # ------------------------------
        adjustment = bar_models.BarInventoryAdjustment(
            bar_id=bar_id,
            item_id=item_id,
            quantity_adjusted=adjustment_data.quantity_adjusted,
            reason=adjustment_data.reason,
            adjusted_by=current_user.username,
            business_id=business_id  # ✅ IMPORTANT FIX
        )

        db.add(adjustment)
        db.commit()
        db.refresh(adjustment)

        return adjustment

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Adjustment failed: {str(e)}"
        )



@router.get("/adjustments", response_model=List[BarInventoryAdjustmentDisplay])
def list_bar_inventory_adjustments(
    bar_id: Optional[int] = None,
    item_id: Optional[int] = None,
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Base query (tenant-safe)
        # ------------------------------
        query = db.query(bar_models.BarInventoryAdjustment).filter(
            bar_models.BarInventoryAdjustment.business_id == business_id
        )

        # ------------------------------
        # 3️⃣ Filters (UNCHANGED LOGIC)
        # ------------------------------
        if bar_id:
            query = query.filter(bar_models.BarInventoryAdjustment.bar_id == bar_id)

        if item_id:
            query = query.filter(bar_models.BarInventoryAdjustment.item_id == item_id)

        if start_date:
            query = query.filter(
                bar_models.BarInventoryAdjustment.adjusted_at >= start_date
            )

        if end_date:
            query = query.filter(
                bar_models.BarInventoryAdjustment.adjusted_at <= end_date
            )

        # ------------------------------
        # 4️⃣ Order + fetch
        # ------------------------------
        adjustments = query.order_by(
            bar_models.BarInventoryAdjustment.adjusted_at.desc()
        ).all()

        return adjustments

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve adjustments: {str(e)}"
        )



# ----------------------------
# Delete Bar Inventory Adjustment (Multi-Tenant)
# ----------------------------
@router.delete("/adjustments/{adjustment_id}", response_model=dict)
def delete_bar_inventory_adjustment(
    adjustment_id: int,
    business_id: Optional[int] = Query(None, description="Super admin can specify business"),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch adjustment (tenant-safe)
        # ------------------------------
        adjustment = (
            db.query(bar_models.BarInventoryAdjustment)
            .filter(
                bar_models.BarInventoryAdjustment.id == adjustment_id,
                bar_models.BarInventoryAdjustment.business_id == business_id
            )
            .first()
        )

        if not adjustment:
            raise HTTPException(status_code=404, detail="Adjustment not found")

        # ------------------------------
        # 3️⃣ Restore inventory (tenant-safe)
        # ------------------------------
        inventory = (
            db.query(bar_models.BarInventory)
            .filter(
                bar_models.BarInventory.bar_id == adjustment.bar_id,
                bar_models.BarInventory.item_id == adjustment.item_id,
                bar_models.BarInventory.business_id == business_id
            )
            .first()
        )

        if inventory:
            inventory.quantity += adjustment.quantity_adjusted

        # ------------------------------
        # 4️⃣ Delete adjustment
        # ------------------------------
        db.delete(adjustment)
        db.commit()

        # ------------------------------
        # 5️⃣ Clean response (NO OBJECT RETURN)
        # ------------------------------
        return {
            "message": "Bar inventory adjustment deleted successfully",
            "adjustment_id": adjustment_id,
            "business_id": business_id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete adjustment: {str(e)}"
        )



""""
@router.delete("/bars/{bar_id}")
def delete_bar(
    bar_id: int,
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(role_required(["admin"]))
):
    bar = db.query(bar_models.Bar).filter_by(id=bar_id).first()
    if not bar:
        raise HTTPException(status_code=404, detail="Bar not found")

    # Optional: Check if this bar has sales or inventory, and block deletion if necessary

    db.delete(bar)
    db.commit()
    return {"detail": "Bar deleted successfully"}

"""

# ----------------------------
# RECEIVED ITEMS
# ----------------------------

from datetime import date

from datetime import date

# ----------------------------
# Store Issue Control (Bar) - Multi-Tenant
# ----------------------------
@router.get("/store-issue-control", response_model=List[dict])
def get_store_items_received(
    bar_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["bar", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Validate bar (tenant-safe)
        # ------------------------------
        if bar_id:
            bar = (
                db.query(bar_models.Bar)
                .filter(
                    bar_models.Bar.id == bar_id,
                    bar_models.Bar.business_id == business_id
                )
                .first()
            )
            if not bar:
                raise HTTPException(status_code=404, detail="Bar not found")

        # ------------------------------
        # 3️⃣ Latest unit price subquery (tenant-safe)
        # ------------------------------
        subquery = (
            db.query(
                store_models.StoreStockEntry.item_id,
                store_models.StoreStockEntry.unit_price
            )
            .filter(
                store_models.StoreStockEntry.business_id == business_id
            )
            .order_by(
                store_models.StoreStockEntry.item_id,
                store_models.StoreStockEntry.purchase_date.desc(),
                store_models.StoreStockEntry.id.desc()
            )
            .distinct(store_models.StoreStockEntry.item_id)
            .subquery()
        )

        # ------------------------------
        # 4️⃣ Main query (tenant-safe)
        # ------------------------------
        query = (
            db.query(
                store_models.StoreIssueItem.item_id,
                store_models.StoreItem.name,
                store_models.StoreItem.unit,
                store_models.StoreIssue.bar_id.label("bar_id"),
                store_models.StoreIssue.issue_date,
                store_models.StoreIssueItem.quantity,
                subquery.c.unit_price
            )
            .join(
                store_models.StoreIssue,
                store_models.StoreIssue.id == store_models.StoreIssueItem.issue_id
            )
            .join(
                store_models.StoreItem,
                store_models.StoreItem.id == store_models.StoreIssueItem.item_id
            )
            .outerjoin(
                subquery,
                subquery.c.item_id == store_models.StoreIssueItem.item_id
            )
            .filter(
                store_models.StoreIssue.issue_to == "bar",                # ✅ IMPORTANT
                store_models.StoreIssue.business_id == business_id,       # ✅ tenant-safe
                store_models.StoreItem.business_id == business_id,        # ✅ tenant-safe
                store_models.StoreItem.item_type == "bar"                 # ✅ only bar items
            )
        )

        # ------------------------------
        # 5️⃣ Filters
        # ------------------------------
        if bar_id:
            query = query.filter(store_models.StoreIssue.bar_id == bar_id)

        if start_date:
            query = query.filter(
                store_models.StoreIssue.issue_date >= start_date
            )

        if end_date:
            query = query.filter(
                store_models.StoreIssue.issue_date < end_date + timedelta(days=1)
            )

        results = query.order_by(
            store_models.StoreIssue.issue_date.desc()
        ).all()

        # ------------------------------
        # 6️⃣ Response
        # ------------------------------
        return [
            {
                "item_id": r.item_id,
                "item_name": r.name,
                "unit": r.unit,
                "bar_id": r.bar_id,
                "issue_date": r.issue_date,
                "quantity": float(r.quantity or 0),
                "unit_price": float(r.unit_price) if r.unit_price else None,
                "total_amount": round(r.quantity * r.unit_price, 2) if r.unit_price else None
            }
            for r in results
        ]

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve store issue control: {str(e)}"
        )


