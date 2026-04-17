# restaurant/router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from datetime import datetime
from typing import List
from typing import Optional
from app.users.auth import get_current_user
from app.users.permissions import role_required  # 👈 permission helper
from app.users.models import User
from fastapi import Query
from datetime import date
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.users import schemas as user_schemas
from app.restaurant import models as restaurant_models
from app.restaurant import schemas as restaurant_schemas
from app.store import  models as store_models
from app.kitchen import models as kitchen_models

from app.restaurant.models import MealOrder, MealOrderItem, Meal, RestaurantLocation
from app.restaurant.schemas import MealOrderCreate, MealOrderDisplay
from app.store.models import StoreStockEntry, StoreItem

from app.restaurant.models import MealOrder, RestaurantSale  # assuming MealOrder is in restaurant.models
from app.restpayment.models import RestaurantSalePayment     # payment model from restpayment folder
from app.restaurant.schemas import RestaurantSaleDisplay     # Sale schema

from app.restaurant.schemas import MealOrderItemDisplay
from app.kitchen import schemas as kitchen_schemas

from sqlalchemy.orm import joinedload

from app.core.db import db_dependency
from app.core.business import resolve_business_id
from app.core.timezone import now_wat  # ✅ USE YOUR CENTRAL HELPER




router = APIRouter()

# ----------------------------
# Restaurant Locations (FINAL WORKING VERSION)
# ----------------------------

# ----------------------------
# Create Location
# ----------------------------
@router.post(
    "/locations",
    response_model=restaurant_schemas.RestaurantLocationDisplay
)
def create_location(
    location: restaurant_schemas.RestaurantLocationCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # ✅ ONLY trigger validation (DO NOT assign)
    resolve_business_id(current_user, business_id)

    # ✅ Prevent duplicate (tenant handled automatically)
    existing = db.query(restaurant_models.RestaurantLocation).filter(
        restaurant_models.RestaurantLocation.name == location.name
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Location '{location.name}' already exists"
        )

    db_location = restaurant_models.RestaurantLocation(
        name=location.name,
        active=getattr(location, "active", True),
        business_id=current_user.business_id if current_user.business_id else business_id
    )

    db.add(db_location)
    db.commit()
    db.refresh(db_location)

    return db_location


# ----------------------------
# List Locations
# ----------------------------
@router.get(
    "/locations",
    response_model=list[restaurant_schemas.RestaurantLocationDisplay]
)
def list_locations(
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # ✅ ONLY resolve (no assignment)
    resolve_business_id(current_user, business_id)

    return (
        db.query(restaurant_models.RestaurantLocation)
        .order_by(restaurant_models.RestaurantLocation.id.asc())
        .all()
    )


# ----------------------------
# Update Location
# ----------------------------
@router.put(
    "/locations/{location_id}",
    response_model=restaurant_schemas.RestaurantLocationDisplay
)
def update_location(
    location_id: int,
    location_update: restaurant_schemas.RestaurantLocationCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # ✅ ONLY resolve
    resolve_business_id(current_user, business_id)

    db_location = db.query(restaurant_models.RestaurantLocation).filter(
        restaurant_models.RestaurantLocation.id == location_id
    ).first()

    if not db_location:
        raise HTTPException(status_code=404, detail="Location not found")

    for key, value in location_update.dict(exclude_unset=True).items():
        setattr(db_location, key, value)

    db.commit()
    db.refresh(db_location)

    return db_location


# ----------------------------
# Delete Location
# ----------------------------
@router.delete("/locations/{location_id}")
def delete_location(
    location_id: int,
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
    # ✅ ONLY resolve
    resolve_business_id(current_user, business_id)

    db_location = db.query(restaurant_models.RestaurantLocation).filter(
        restaurant_models.RestaurantLocation.id == location_id
    ).first()

    if not db_location:
        raise HTTPException(status_code=404, detail="Location not found")

    db.delete(db_location)
    db.commit()

    return {
        "detail": f"Location '{db_location.name}' deleted successfully"
    }



# ----------------------------
# Toggle Location Active Status (MULTI-TENANT SAFE)
# ----------------------------
@router.patch(
    "/locations/{location_id}",
    response_model=restaurant_schemas.RestaurantLocationDisplay
)
def toggle_location_active(
    location_id: int,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # ✅ Validate tenant (DO NOT assign)
    resolve_business_id(current_user, business_id)

    # ✅ Fetch location (tenant filter handled automatically)
    location = (
        db.query(restaurant_models.RestaurantLocation)
        .filter(restaurant_models.RestaurantLocation.id == location_id)
        .first()
    )

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # ✅ Toggle status
    location.active = not location.active

    db.commit()
    db.refresh(location)

    return location

#

@router.get(
    "/items/simple",
    response_model=List[restaurant_schemas.RestaurantMealItem]
)
def get_restaurant_items(
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    """
    Optimized version:
    - Uses DISTINCT ON (PostgreSQL)
    - Avoids heavy GROUP BY
    - Much faster on large datasets
    """

    # ✅ Resolve tenant
    resolve_business_id(current_user, business_id)

    # ------------------------------
    # 1️⃣ Latest menu per item (FAST 🔥)
    # ------------------------------
    latest_menu_subquery = (
        db.query(
            kitchen_models.KitchenMenu.item_id,
            kitchen_models.KitchenMenu.selling_price
        )
        .distinct(kitchen_models.KitchenMenu.item_id)
        .order_by(
            kitchen_models.KitchenMenu.item_id,
            kitchen_models.KitchenMenu.id.desc()
        )
        .subquery()
    )

    # ------------------------------
    # 2️⃣ Main query
    # ------------------------------
    items = (
        db.query(
            store_models.StoreItem.id.label("item_id"),
            store_models.StoreItem.name.label("item_name"),
            store_models.StoreItem.item_type.label("item_type"),
            latest_menu_subquery.c.selling_price
        )
        .outerjoin(
            latest_menu_subquery,
            latest_menu_subquery.c.item_id == store_models.StoreItem.id
        )
        .filter(store_models.StoreItem.item_type == "kitchen")
        .order_by(store_models.StoreItem.name.asc())
        .all()
    )

    # ------------------------------
    # 3️⃣ Response
    # ------------------------------
    return [
        restaurant_schemas.RestaurantMealItem(
            id=item.item_id,
            name=item.item_name,
            price=item.selling_price or 0,
            item_type=item.item_type
        )
        for item in items
    ]


@router.get(
    "/items/store-selling",
    response_model=List[restaurant_schemas.RestaurantMealStoreItem]
)
def get_restaurant_items_from_store(
    search: Optional[str] = Query(
        None,
        description="Search item name",
        example="rice"
    ),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    """
    Fetch kitchen/store items using StoreItem.selling_price.
    - Tenant-safe (middleware handles filtering)
    - Supports search
    """

    # ✅ Resolve tenant (IMPORTANT)
    resolve_business_id(current_user, business_id)

    # ------------------------------
    # 1️⃣ Base query
    # ------------------------------
    query = (
        db.query(
            store_models.StoreItem.id,
            store_models.StoreItem.name,
            store_models.StoreItem.selling_price,
        )
        .filter(
            store_models.StoreItem.item_type.in_(["kitchen", "meal", "food"])
        )
    )

    # ------------------------------
    # 2️⃣ Search (optimized)
    # ------------------------------
    if search:
        query = query.filter(
            store_models.StoreItem.name.ilike(f"%{search.strip()}%")
        )

    # ------------------------------
    # 3️⃣ Execute
    # ------------------------------
    items = (
        query
        .order_by(store_models.StoreItem.name.asc())
        .all()
    )

    # ------------------------------
    # 4️⃣ Response
    # ------------------------------
    return [
        restaurant_schemas.RestaurantMealStoreItem(
            id=item.id,
            name=item.name,
            selling_price=float(item.selling_price or 0)
        )
        for item in items
    ]



@router.post(
    "/meal-orders",
    response_model=restaurant_schemas.MealOrderDisplay
)
def create_meal_order(
    order: restaurant_schemas.MealOrderCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant (FIXED)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Validate location
        # ------------------------------
        location = db.query(restaurant_models.RestaurantLocation).filter(
            restaurant_models.RestaurantLocation.id == order.location_id
        ).first()

        if not location:
            raise HTTPException(404, "Restaurant location not found")

        # ------------------------------
        # 3️⃣ Validate kitchen
        # ------------------------------
        kitchen = db.query(kitchen_models.Kitchen).filter(
            kitchen_models.Kitchen.id == order.kitchen_id
        ).first()

        if not kitchen:
            raise HTTPException(404, "Selected kitchen not found")

        # ------------------------------
        # 4️⃣ Allowed items
        # ------------------------------
        kitchen_items = db.query(store_models.StoreItem).filter(
            store_models.StoreItem.item_type.in_(["kitchen", "meal", "food"])
        ).all()

        kitchen_map = {item.id: item for item in kitchen_items}

        # ------------------------------
        # 5️⃣ Validate items
        # ------------------------------
        for it in order.items:
            if it.quantity <= 0:
                raise HTTPException(
                    400,
                    f"Invalid quantity for item {it.store_item_id}"
                )

            if it.store_item_id not in kitchen_map:
                raise HTTPException(
                    404,
                    f"Item {it.store_item_id} is not valid"
                )

        # ------------------------------
        # 6️⃣ Create order (FIXED business_id)
        # ------------------------------
        db_order = restaurant_models.MealOrder(
            order_type=order.order_type,
            guest_name=order.guest_name,
            room_number=order.room_number,
            location_id=order.location_id,
            kitchen_id=order.kitchen_id,
            status=order.status or "open",
            created_by=current_user.id,
            created_at=now_wat(),
            business_id=business_id   # 🔥 FIXED
        )

        db.add(db_order)
        db.flush()

        # ------------------------------
        # 7️⃣ Process items
        # ------------------------------
        for it in order.items:
            store_item = kitchen_map[it.store_item_id]
            qty = it.quantity

            inventory = db.query(kitchen_models.KitchenInventory).filter(
                kitchen_models.KitchenInventory.kitchen_id == order.kitchen_id,
                kitchen_models.KitchenInventory.item_id == store_item.id
            ).first()

            if not inventory:
                inventory = kitchen_models.KitchenInventory(
                    kitchen_id=order.kitchen_id,
                    item_id=store_item.id,
                    quantity=0,
                    business_id=business_id   # 🔥 FIXED
                )
                db.add(inventory)

            # Allow negative stock
            inventory.quantity -= qty

            # Price logic
            price_per_unit = (
                it.price_per_unit
                if it.price_per_unit and it.price_per_unit > 0
                else (store_item.selling_price or 0)
            )

            db_item = restaurant_models.MealOrderItem(
                order_id=db_order.id,
                store_item_id=store_item.id,
                quantity=qty,
                store_qty_used=qty,
                item_name=store_item.name,
                price_per_unit=price_per_unit,
                total_price=price_per_unit * qty,
                business_id=business_id   # 🔥 FIXED
            )

            db.add(db_item)

        # ------------------------------
        # 8️⃣ Commit
        # ------------------------------
        db.commit()
        db.refresh(db_order)

        return db_order

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Meal order creation failed: {str(e)}"
        )





from sqlalchemy.orm import joinedload

@router.get(
    "/meal-orders",
    response_model=List[restaurant_schemas.MealOrderDisplay]
)
def list_meal_orders(
    status: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    location_id: Optional[int] = Query(None),
    kitchen_id: Optional[int] = Query(None),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    # ------------------------------
    # 1️⃣ Resolve tenant
    # ------------------------------
    resolve_business_id(current_user, business_id)

    # ------------------------------
    # 2️⃣ Base query (OPTIMIZED with eager loading)
    # ------------------------------
    query = (
        db.query(restaurant_models.MealOrder)
        .options(joinedload(restaurant_models.MealOrder.items))
    )

    # ------------------------------
    # 3️⃣ Filters
    # ------------------------------
    if location_id:
        query = query.filter(restaurant_models.MealOrder.location_id == location_id)

    if kitchen_id:
        query = query.filter(restaurant_models.MealOrder.kitchen_id == kitchen_id)

    if status:
        query = query.filter(restaurant_models.MealOrder.status == status)

    if start_date:
        query = query.filter(
            restaurant_models.MealOrder.created_at >= datetime.combine(start_date, datetime.min.time())
        )

    if end_date:
        query = query.filter(
            restaurant_models.MealOrder.created_at <= datetime.combine(end_date, datetime.max.time())
        )

    # ------------------------------
    # 4️⃣ Execute query
    # ------------------------------
    orders = query.order_by(
        restaurant_models.MealOrder.created_at.desc()
    ).all()

    # ------------------------------
    # 5️⃣ Response mapping
    # ------------------------------
    return [
        restaurant_schemas.MealOrderDisplay(
            id=o.id,
            location_id=o.location_id,
            kitchen_id=o.kitchen_id,
            order_type=o.order_type,
            room_number=o.room_number,
            guest_name=o.guest_name,
            status=o.status,
            created_at=o.created_at,
            items=[
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in o.items
            ]
        )
        for o in orders
    ]




@router.put(
    "/meal-orders/{order_id}",
    response_model=restaurant_schemas.MealOrderDisplay
)
def update_meal_order(
    order_id: int,
    data: restaurant_schemas.MealOrderCreate,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch order (tenant-safe)
        # ------------------------------
        order = (
            db.query(restaurant_models.MealOrder)
            .filter(
                restaurant_models.MealOrder.id == order_id,
                restaurant_models.MealOrder.business_id == business_id
            )
            .first()
        )

        if not order:
            raise HTTPException(status_code=404, detail="Meal order not found")

        if order.status == "closed":
            raise HTTPException(status_code=400, detail="Closed orders cannot be edited")

        # ------------------------------
        # 3️⃣ Validate location
        # ------------------------------
        location = (
            db.query(restaurant_models.RestaurantLocation)
            .filter(
                restaurant_models.RestaurantLocation.id == data.location_id,
                restaurant_models.RestaurantLocation.business_id == business_id
            )
            .first()
        )

        if not location:
            raise HTTPException(status_code=404, detail="Restaurant location not found")

        # ------------------------------
        # 4️⃣ Validate kitchen
        # ------------------------------
        kitchen = (
            db.query(kitchen_models.Kitchen)
            .filter(
                kitchen_models.Kitchen.id == data.kitchen_id,
                kitchen_models.Kitchen.business_id == business_id
            )
            .first()
        )

        if not kitchen:
            raise HTTPException(status_code=404, detail="Kitchen not found")

        # ------------------------------
        # 5️⃣ Load allowed items (single query)
        # ------------------------------
        kitchen_items = (
            db.query(store_models.StoreItem)
            .filter(
                store_models.StoreItem.item_type.in_(["kitchen", "meal", "food"]),
                store_models.StoreItem.business_id == business_id
            )
            .all()
        )

        kitchen_map = {i.id: i for i in kitchen_items}

        # ------------------------------
        # 6️⃣ RESTORE OLD STOCK (bulk-safe logic)
        # ------------------------------
        old_items = (
            db.query(restaurant_models.MealOrderItem)
            .filter(restaurant_models.MealOrderItem.order_id == order.id)
            .all()
        )

        for old in old_items:
            inv = (
                db.query(kitchen_models.KitchenInventory)
                .filter(
                    kitchen_models.KitchenInventory.kitchen_id == order.kitchen_id,
                    kitchen_models.KitchenInventory.item_id == old.store_item_id,
                    kitchen_models.KitchenInventory.business_id == business_id
                )
                .first()
            )

            if inv:
                inv.quantity += old.store_qty_used

        # delete old items
        db.query(restaurant_models.MealOrderItem).filter(
            restaurant_models.MealOrderItem.order_id == order.id
        ).delete()

        db.flush()

        # ------------------------------
        # 7️⃣ VALIDATE NEW ITEMS
        # ------------------------------
        for it in data.items:
            if it.quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid quantity for item {it.store_item_id}"
                )

            if it.store_item_id not in kitchen_map:
                raise HTTPException(
                    status_code=404,
                    detail=f"Item {it.store_item_id} not allowed"
                )

        # ------------------------------
        # 8️⃣ UPDATE ORDER FIELDS
        # ------------------------------
        order.order_type = data.order_type
        order.room_number = data.room_number
        order.guest_name = data.guest_name
        order.location_id = data.location_id
        order.kitchen_id = data.kitchen_id

        # ------------------------------
        # 9️⃣ APPLY NEW ITEMS + DEDUCT STOCK
        # ------------------------------
        for it in data.items:
            store_item = kitchen_map[it.store_item_id]
            qty = it.quantity

            inv = (
                db.query(kitchen_models.KitchenInventory)
                .filter(
                    kitchen_models.KitchenInventory.kitchen_id == data.kitchen_id,
                    kitchen_models.KitchenInventory.item_id == store_item.id,
                    kitchen_models.KitchenInventory.business_id == business_id
                )
                .first()
            )

            if not inv:
                inv = kitchen_models.KitchenInventory(
                    kitchen_id=data.kitchen_id,
                    item_id=store_item.id,
                    quantity=0,
                    business_id=business_id
                )
                db.add(inv)

            # allow negative stock
            inv.quantity -= qty

            price = (
                it.price_per_unit
                if it.price_per_unit and it.price_per_unit > 0
                else (store_item.selling_price or 0)
            )

            db.add(
                restaurant_models.MealOrderItem(
                    order_id=order.id,
                    store_item_id=store_item.id,
                    quantity=qty,
                    store_qty_used=qty,
                    item_name=store_item.name,
                    price_per_unit=price,
                    total_price=price * qty,
                    business_id=business_id
                )
            )

        # ------------------------------
        # 🔟 FINAL COMMIT
        # ------------------------------
        db.commit()
        db.refresh(order)

        # ------------------------------
        # 1️⃣1️⃣ RESPONSE
        # ------------------------------
        return restaurant_schemas.MealOrderDisplay(
            id=order.id,
            location_id=order.location_id,
            kitchen_id=order.kitchen_id,
            order_type=order.order_type,
            room_number=order.room_number,
            guest_name=order.guest_name,
            status=order.status,
            created_at=order.created_at,
            items=[
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in order.items
            ],
        )

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not update meal order: {str(e)}"
        )



@router.delete(
    "/meal-orders/{order_id}",
    response_model=dict
)
def delete_meal_order(
    order_id: int,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch order (tenant-safe)
        # ------------------------------
        db_order = (
            db.query(restaurant_models.MealOrder)
            .filter(
                restaurant_models.MealOrder.id == order_id,
                restaurant_models.MealOrder.business_id == business_id
            )
            .first()
        )

        if not db_order:
            raise HTTPException(
                status_code=404,
                detail="Meal order not found"
            )

        # ------------------------------
        # 3️⃣ Restore inventory BEFORE deletion
        # ------------------------------
        order_items = (
            db.query(restaurant_models.MealOrderItem)
            .filter(
                restaurant_models.MealOrderItem.order_id == db_order.id,
                restaurant_models.MealOrderItem.business_id == business_id
            )
            .all()
        )

        for item in order_items:
            inventory = (
                db.query(kitchen_models.KitchenInventory)
                .filter(
                    kitchen_models.KitchenInventory.kitchen_id == db_order.kitchen_id,
                    kitchen_models.KitchenInventory.item_id == item.store_item_id,
                    kitchen_models.KitchenInventory.business_id == business_id
                )
                .first()
            )

            if inventory:
                # 🔥 restore stock
                inventory.quantity += item.store_qty_used

        # ------------------------------
        # 4️⃣ Delete order (cascade removes items)
        # ------------------------------
        db.delete(db_order)
        db.commit()

        return {
            "detail": "Meal order deleted successfully",
            "restored_items": len(order_items)
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete meal order: {str(e)}"
        )





@router.post("/map")
def map_store_item_to_meal(
    store_item_id: int,
    quantity_used: float = 1,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user=Depends(role_required(["restaurant", "admin", "super_admin"]))
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Validate store item
        # ------------------------------
        store_item = (
            db.query(store_models.StoreItem)
            .filter(
                store_models.StoreItem.id == store_item_id,
                store_models.StoreItem.business_id == business_id
            )
            .first()
        )

        if not store_item:
            raise HTTPException(status_code=404, detail="Store item not found")

        # ------------------------------
        # 3️⃣ Prevent duplicate mapping
        # ------------------------------
        existing = (
            db.query(restaurant_models.MealStoreItem)
            .filter(
                restaurant_models.MealStoreItem.store_item_id == store_item_id,
                restaurant_models.MealStoreItem.business_id == business_id
            )
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail="This item is already mapped"
            )

        # ------------------------------
        # 4️⃣ Create mapping
        # ------------------------------
        mapping = restaurant_models.MealStoreItem(
            store_item_id=store_item_id,
            quantity_used=quantity_used,
            business_id=business_id
        )

        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        # ------------------------------
        # 5️⃣ Response
        # ------------------------------
        return {
            "message": "Mapping created successfully",
            "data": {
                "id": mapping.id,
                "store_item_id": mapping.store_item_id,
                "quantity_used": mapping.quantity_used
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Mapping failed: {str(e)}"
        )




from sqlalchemy.orm import joinedload



@router.get("/sales", response_model=dict)
def list_sales(
    status: Optional[str] = Query(None, description="Filter: unpaid, partial, paid"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    location_id: Optional[int] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Base query (JOIN eager load to reduce N+1)
        # -----------------------------
        query = (
            db.query(restaurant_models.RestaurantSale)
            .filter(restaurant_models.RestaurantSale.business_id == business_id)
        )

        # -----------------------------
        # 3️⃣ Filters
        # -----------------------------
        if status:
            query = query.filter(restaurant_models.RestaurantSale.status == status)

        if location_id:
            query = query.filter(restaurant_models.RestaurantSale.location_id == location_id)

        if start_date:
            start_dt = datetime.combine(start_date, datetime.min.time())
            query = query.filter(restaurant_models.RestaurantSale.served_at >= start_dt)

        if end_date:
            end_dt = datetime.combine(end_date, datetime.max.time())
            query = query.filter(restaurant_models.RestaurantSale.served_at <= end_dt)

        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Start date cannot be after end date")

        # -----------------------------
        # 4️⃣ Execute query
        # -----------------------------
        sales = query.order_by(
            restaurant_models.RestaurantSale.served_at.desc().nullslast(),
            restaurant_models.RestaurantSale.id.desc()
        ).all()

        # -----------------------------
        # 5️⃣ Build response (optimized loop)
        # -----------------------------
        result = []
        summary_sales = 0.0
        summary_paid = 0.0
        summary_balance = 0.0

        for sale in sales:
            order = sale.order

            amount_paid = sum(
                (p.amount_paid or 0)
                for p in sale.payments
                if not getattr(p, "is_void", False)
            )

            total = sale.total_amount or 0
            balance = total - amount_paid

            # computed status (source of truth)
            if amount_paid <= 0:
                computed_status = "unpaid"
            elif amount_paid < total:
                computed_status = "partial"
            else:
                computed_status = "paid"

            items = [
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in (order.items if order else [])
            ]

            result.append({
                "id": sale.id,
                "order_id": sale.order_id,
                "location_id": sale.location_id,
                "guest_name": order.guest_name if order else None,
                "served_by": sale.served_by,
                "total_amount": total,
                "amount_paid": amount_paid,
                "balance": balance,
                "status": computed_status,
                "served_at": sale.served_at,
                "created_at": sale.created_at,
                "items": items,
            })

            summary_sales += total
            summary_paid += amount_paid
            summary_balance += balance

        # -----------------------------
        # 6️⃣ Summary
        # -----------------------------
        summary = {
            "total_sales_amount": summary_sales,
            "total_paid_amount": summary_paid,
            "total_balance": summary_balance,
        }

        return {
            "sales": result,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load sales: {str(e)}"
        )



@router.get("/sales/items-summary", response_model=dict)
def summarize_items_sold(
    status: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    location_id: Optional[int] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Base query (optimized joins)
        # -----------------------------
        query = (
            db.query(RestaurantSale)
            .join(RestaurantSale.order)
            .filter(RestaurantSale.business_id == business_id)
            .options(
                joinedload(RestaurantSale.order)
                .joinedload(MealOrder.items)
                .joinedload(MealOrderItem.store_item),
                joinedload(RestaurantSale.payments)
            )
        )

        # -----------------------------
        # 3️⃣ Filters
        # -----------------------------
        if status:
            query = query.filter(RestaurantSale.status == status)

        if location_id:
            query = query.filter(MealOrder.location_id == location_id)

        if start_date:
            query = query.filter(
                RestaurantSale.served_at >= datetime.combine(start_date, datetime.min.time())
            )

        if end_date:
            query = query.filter(
                RestaurantSale.served_at <= datetime.combine(end_date, datetime.max.time())
            )

        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Start date cannot be after end date")

        # -----------------------------
        # 4️⃣ Execute query
        # -----------------------------
        sales = query.all()

        # -----------------------------
        # 5️⃣ ITEM + PAYMENT AGGREGATION
        # -----------------------------
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

        # -----------------------------
        # 6️⃣ LOOP SALES
        # -----------------------------
        for sale in sales:
            order = sale.order
            if not order:
                continue

            # -------------------------
            # ITEM SUMMARY
            # -------------------------
            for item in order.items:
                store_item = item.store_item
                if not store_item:
                    continue

                name = store_item.name
                price = float(item.price_per_unit or store_item.selling_price or 0)
                qty = float(item.quantity or 0)
                amount = float(item.total_price or (qty * price))

                key = (name, price)

                if key not in item_summary:
                    item_summary[key] = {
                        "item": name,
                        "qty": 0.0,
                        "price": price,
                        "amount": 0.0,
                    }

                item_summary[key]["qty"] += qty
                item_summary[key]["amount"] += amount
                grand_total += amount

            # -------------------------
            # PAYMENT SUMMARY
            # -------------------------
            total_paid = sum(
                float(p.amount_paid or 0)
                for p in sale.payments
                if not getattr(p, "is_void", False)
            )

            total_sales = float(sale.total_amount or 0)
            balance = total_sales - total_paid

            payment_summary["total_sales"] += total_sales
            payment_summary["total_paid"] += total_paid
            payment_summary["total_due"] += balance

            for p in sale.payments:
                if getattr(p, "is_void", False):
                    continue

                amount = float(p.amount_paid or 0)
                mode = (p.payment_mode or "").upper()
                bank = (getattr(p, "bank", "") or "").upper().strip()

                if mode == "CASH":
                    payment_summary["total_cash"] += amount
                elif mode == "POS":
                    payment_summary["total_pos"] += amount
                elif mode == "TRANSFER":
                    payment_summary["total_transfer"] += amount

                if bank:
                    if bank not in payment_summary["banks"]:
                        payment_summary["banks"][bank] = {"pos": 0.0, "transfer": 0.0}

                    if mode == "POS":
                        payment_summary["banks"][bank]["pos"] += amount
                    elif mode == "TRANSFER":
                        payment_summary["banks"][bank]["transfer"] += amount

        # -----------------------------
        # 7️⃣ RESPONSE FORMAT
        # -----------------------------
        items = list(item_summary.values())

        return {
            "items": items,
            "items_summary": {
                "grand_total": grand_total,
                "total_items": len(items),
            },
            "payment_summary": payment_summary
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate sales summary: {str(e)}"
        )


@router.get("/sales/outstanding", response_model=dict)
def list_outstanding_sales(
    location_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Base query (tenant-safe)
        # -----------------------------
        query = (
            db.query(restaurant_models.RestaurantSale)
            .filter(restaurant_models.RestaurantSale.business_id == business_id)
        )

        # -----------------------------
        # 3️⃣ Date filters
        # -----------------------------
        if start_date:
            query = query.filter(
                restaurant_models.RestaurantSale.served_at >= datetime.combine(
                    start_date, datetime.min.time()
                )
            )

        if end_date:
            query = query.filter(
                restaurant_models.RestaurantSale.served_at <= datetime.combine(
                    end_date, datetime.max.time()
                )
            )

        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Start date cannot be after end date")

        # -----------------------------
        # 4️⃣ Execute query
        # -----------------------------
        sales = query.order_by(
            restaurant_models.RestaurantSale.served_at.desc().nullslast(),
            restaurant_models.RestaurantSale.id.desc()
        ).all()

        # -----------------------------
        # 5️⃣ PROCESS DATA
        # -----------------------------
        result = []
        total_sales_amount = 0.0
        total_paid_amount = 0.0
        total_balance = 0.0

        for sale in sales:
            order = sale.order

            if not order:
                continue

            # -------------------------
            # Location filter (post-load safe)
            # -------------------------
            if location_id and order.location_id != location_id:
                continue

            # -------------------------
            # Payments
            # -------------------------
            amount_paid = sum(
                float(p.amount_paid or 0)
                for p in sale.payments
                if not getattr(p, "is_void", False)
            )

            total = float(sale.total_amount or 0)
            balance = total - amount_paid

            # -------------------------
            # OUTSTANDING ONLY
            # -------------------------
            if balance <= 0:
                continue

            # -------------------------
            # Items
            # -------------------------
            items_display = [
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in order.items
            ]

            # -------------------------
            # Totals
            # -------------------------
            total_sales_amount += total
            total_paid_amount += amount_paid
            total_balance += balance

            result.append({
                "id": sale.id,
                "order_id": sale.order_id,
                "guest_name": order.guest_name,
                "location_id": order.location_id,
                "served_by": sale.served_by,
                "total_amount": total,
                "amount_paid": amount_paid,
                "balance": balance,
                "status": "outstanding",
                "served_at": sale.served_at,
                "created_at": sale.created_at,
                "items": items_display,
            })

        # -----------------------------
        # 6️⃣ SUMMARY
        # -----------------------------
        summary = {
            "total_sales_amount": total_sales_amount,
            "total_paid_amount": total_paid_amount,
            "total_balance": total_balance,
            "total_outstanding_sales": len(result),
        }

        return {
            "sales": result,
            "summary": summary
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch outstanding sales: {str(e)}"
        )



@router.get("/sales/{sale_id}", response_model=restaurant_schemas.RestaurantSaleDisplay)
def get_sale(
    sale_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Fetch sale (tenant-safe)
        # -----------------------------
        sale = (
            db.query(restaurant_models.RestaurantSale)
            .filter(
                restaurant_models.RestaurantSale.id == sale_id,
                restaurant_models.RestaurantSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")

        # -----------------------------
        # 3️⃣ Load related order
        # -----------------------------
        order = sale.order

        items_display = []
        guest_name = None
        location_id = None

        if order:
            guest_name = order.guest_name
            location_id = order.location_id

            items_display = [
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in order.items
            ]

        # -----------------------------
        # 4️⃣ Payments calculation
        # -----------------------------
        amount_paid = sum(
            float(p.amount_paid or 0)
            for p in sale.payments
            if not getattr(p, "is_void", False)
        )

        total = float(sale.total_amount or 0)
        balance = total - amount_paid

        # -----------------------------
        # 5️⃣ RESPONSE
        # -----------------------------
        return restaurant_schemas.RestaurantSaleDisplay(
            id=sale.id,
            order_id=sale.order_id,
            guest_name=guest_name,
            location_id=location_id,
            served_by=sale.served_by,
            total_amount=total,
            amount_paid=amount_paid,
            balance=balance,
            status=sale.status,
            served_at=sale.served_at,
            created_at=sale.created_at,
            items=items_display
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch sale: {str(e)}"
        )


@router.delete("/sales/{sale_id}")
def delete_sale(
    sale_id: int,
    business_id: Optional[int] = Query(None),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Fetch sale (tenant-safe)
        # -----------------------------
        sale = (
            db.query(restaurant_models.RestaurantSale)
            .filter(
                restaurant_models.RestaurantSale.id == sale_id,
                restaurant_models.RestaurantSale.business_id == business_id
            )
            .first()
        )

        if not sale:
            raise HTTPException(status_code=404, detail="Sale not found")

        # -----------------------------
        # 3️⃣ Prevent delete if payments exist (RELATIONSHIP SAFE ✅)
        # -----------------------------
        has_valid_payment = any(
            (p.amount_paid or 0) > 0 and not getattr(p, "is_void", False)
            for p in (sale.payments or [])
        )

        if has_valid_payment:
            raise HTTPException(
                status_code=400,
                detail="Sale has attached payments and cannot be deleted"
            )

        # -----------------------------
        # 4️⃣ Reopen linked order
        # -----------------------------
        if sale.order:
            sale.order.status = "open"
            db.add(sale.order)

        # -----------------------------
        # 5️⃣ Delete sale
        # -----------------------------
        db.delete(sale)

        # -----------------------------
        # 6️⃣ Commit
        # -----------------------------
        db.commit()

        return {
            "detail": f"Sale {sale_id} deleted successfully",
            "restored_order": sale.order.id if sale.order else None
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete sale: {str(e)}"
        )



@router.post(
    "/sales/from-order/{order_id}",
    response_model=restaurant_schemas.RestaurantSaleDisplay
)
def create_sale_from_order(
    order_id: int,
    served_by: str,
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve tenant
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ------------------------------
        # 2️⃣ Fetch order (tenant-safe)
        # ------------------------------
        order = (
            db.query(restaurant_models.MealOrder)
            .filter(
                restaurant_models.MealOrder.id == order_id,
                restaurant_models.MealOrder.business_id == business_id
            )
            .first()
        )

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != "open":
            raise HTTPException(status_code=400, detail="Order already closed")

        if not order.kitchen_id:
            raise HTTPException(status_code=400, detail="Order not linked to kitchen")

        # ------------------------------
        # 3️⃣ Compute total
        # ------------------------------
        total = sum(float(i.total_price or 0) for i in order.items)

        # ------------------------------
        # 4️⃣ Create sale
        # ------------------------------
        sale = restaurant_models.RestaurantSale(
            order_id=order.id,
            location_id=order.location_id,
            guest_name=order.guest_name,
            served_by=served_by,
            total_amount=total,
            status="unpaid",
            served_at=now_wat(),
            business_id=business_id
        )

        db.add(sale)
        db.flush()

        # ------------------------------
        # 5️⃣ Create store issue record
        # ------------------------------
        store_issue = store_models.StoreIssue(
            issue_to="kitchen",
            kitchen_id=order.kitchen_id,
            issued_by_id=current_user.id,
            issue_date=now_wat(),
            business_id=business_id
        )

        db.add(store_issue)
        db.flush()

        # ------------------------------
        # 6️⃣ STOCK DEDUCTION (FIFO OPTIMIZED)
        # ------------------------------
        store_item_ids = [i.store_item_id for i in order.items]

        stock_entries = (
            db.query(store_models.StoreStockEntry)
            .filter(
                store_models.StoreStockEntry.item_id.in_(store_item_ids),
                store_models.StoreStockEntry.quantity > 0,
                store_models.StoreStockEntry.business_id == business_id
            )
            .order_by(
                store_models.StoreStockEntry.purchase_date.asc(),
                store_models.StoreStockEntry.id.asc()
            )
            .with_for_update()
            .all()
        )

        stock_map = {}
        for entry in stock_entries:
            stock_map.setdefault(entry.item_id, []).append(entry)

        # ------------------------------
        # 7️⃣ Process order items
        # ------------------------------
        for item in order.items:
            store_item = item.store_item
            if not store_item:
                continue

            qty_to_deduct = float(item.store_qty_used or item.quantity or 0)
            if qty_to_deduct <= 0:
                continue

            remaining = qty_to_deduct

            for entry in stock_map.get(store_item.id, []):
                if remaining <= 0:
                    break

                available = float(entry.quantity or 0)
                if available <= 0:
                    continue

                if available >= remaining:
                    used = remaining
                    entry.quantity = available - remaining
                    remaining = 0
                else:
                    used = available
                    entry.quantity = 0
                    remaining -= available

                db.add(
                    store_models.StoreIssueItem(
                        issue_id=store_issue.id,
                        item_id=store_item.id,
                        quantity=used,
                        business_id=business_id
                    )
                )

            # optional: log insufficient stock
            if remaining > 0:
                pass

        # ------------------------------
        # 8️⃣ CLOSE ORDER
        # ------------------------------
        order.status = "closed"

        # ------------------------------
        # 9️⃣ COMMIT
        # ------------------------------
        db.commit()
        db.refresh(sale)

        # ------------------------------
        # 🔟 RESPONSE BUILD
        # ------------------------------
        amount_paid = sum(p.amount for p in sale.payments) if sale.payments else 0
        balance = (sale.total_amount or 0) - amount_paid

        return restaurant_schemas.RestaurantSaleDisplay(
            id=sale.id,
            order_id=sale.order_id,
            location_id=sale.location_id,
            guest_name=sale.guest_name,
            served_by=sale.served_by,
            total_amount=sale.total_amount,
            amount_paid=amount_paid,
            balance=balance,
            status=sale.status,
            served_at=sale.served_at,
            created_at=sale.created_at,
            items=[
                restaurant_schemas.MealOrderItemDisplay(
                    store_item_id=i.store_item_id,
                    item_name=i.item_name,
                    quantity=i.quantity,
                    price_per_unit=i.price_per_unit,
                    total_price=i.total_price,
                )
                for i in order.items
            ]
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not create sale from order: {str(e)}"
        )



from sqlalchemy.orm import joinedload

@router.get("/open")
def list_open_meal_orders(
    location_id: Optional[int] = Query(None, description="Filter by location id"),
    business_id: Optional[int] = Query(
        None,
        description="Super admin must provide business_id",
        example=1
    ),
    db: Session = Depends(db_dependency),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["restaurant", "admin", "super_admin"])
    )
):
    try:
        # -----------------------------
        # 1️⃣ Resolve tenant
        # -----------------------------
        business_id = resolve_business_id(current_user, business_id)

        # -----------------------------
        # 2️⃣ Base query (optimized 🔥)
        # -----------------------------
        query = (
            db.query(restaurant_models.MealOrder)
            .options(
                joinedload(restaurant_models.MealOrder.items),
                joinedload(restaurant_models.MealOrder.location),
                joinedload(restaurant_models.MealOrder.kitchen),
            )
            .filter(
                restaurant_models.MealOrder.status == "open",
                restaurant_models.MealOrder.business_id == business_id
            )
        )

        if location_id:
            query = query.filter(
                restaurant_models.MealOrder.location_id == location_id
            )

        orders = query.order_by(
            restaurant_models.MealOrder.id.asc()
        ).all()

        # -----------------------------
        # 3️⃣ Build response
        # -----------------------------
        result = []
        total_amount = 0.0

        for order in orders:
            order_total = 0.0

            items_display = []
            for item in order.items:
                item_total = float(item.total_price or 0)
                order_total += item_total

                items_display.append(
                    restaurant_schemas.MealOrderItemDisplay(
                        id=item.id,
                        meal_id=item.meal_id,
                        meal_name=item.meal.name if item.meal else None,  # ✅ no extra query
                        store_item_id=item.store_item_id,
                        item_name=item.item_name,
                        quantity=item.quantity,
                        price_per_unit=item.price_per_unit,
                        total_price=item_total,
                        store_qty_used=item.store_qty_used,
                    )
                )

            total_amount += order_total

            result.append(
                restaurant_schemas.MealOrderDisplay(
                    id=order.id,
                    location_id=order.location_id,
                    kitchen_id=order.kitchen_id,
                    location_name=order.location.name if order.location else None,
                    kitchen_name=order.kitchen.name if order.kitchen else None,
                    order_type=order.order_type,
                    room_number=order.room_number,
                    guest_name=order.guest_name,
                    status=order.status,
                    created_at=order.created_at,
                    items=items_display,
                )
            )

        # -----------------------------
        # 4️⃣ Final response
        # -----------------------------
        return {
            "total_entries": len(result),
            "total_amount": total_amount,
            "orders": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch open meal orders: {str(e)}"
        )





@router.get("/kitchen-balance-stock", response_model=List[kitchen_schemas.KitchenStockBalance])
def get_kitchen_stock_balance(
    item_id: Optional[int] = Query(None),
    kitchen_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: user_schemas.UserDisplaySchema = Depends(
        role_required(["store", "restaurant", "admin", "super_admin"])
    )
):
    try:
        # ------------------------------
        # 1️⃣ Resolve business (same as bar)
        # ------------------------------
        business_id = resolve_business_id(current_user, business_id)

        # ============================================
        # 🔍 GET FILTERED ITEM IDs
        # ============================================
        item_query = db.query(store_models.StoreItem.id).filter(
            store_models.StoreItem.business_id == business_id
        )

        if item_id:
            item_query = item_query.filter(store_models.StoreItem.id == item_id)

        if search:
            item_query = item_query.filter(
                store_models.StoreItem.name.ilike(f"%{search}%")
            )

        filtered_item_ids = [row.id for row in item_query.all()]

        if search and not filtered_item_ids:
            return []

        # ============================================
        # 1️⃣ TOTAL ISSUED (Store → Kitchen)
        # ============================================
        issued_query = (
            db.query(
                store_models.StoreIssueItem.item_id,
                store_models.StoreIssue.kitchen_id,
                func.sum(store_models.StoreIssueItem.quantity).label("total_issued")
            )
            .join(store_models.StoreIssue)
            .filter(
                store_models.StoreIssue.issue_to == "kitchen",
                store_models.StoreIssue.business_id == business_id
            )
        )

        if filtered_item_ids:
            issued_query = issued_query.filter(
                store_models.StoreIssueItem.item_id.in_(filtered_item_ids)
            )

        if kitchen_id:
            issued_query = issued_query.filter(store_models.StoreIssue.kitchen_id == kitchen_id)
        if start_date:
            issued_query = issued_query.filter(store_models.StoreIssue.issue_date >= start_date)
        if end_date:
            issued_query = issued_query.filter(store_models.StoreIssue.issue_date <= end_date)

        issued_query = issued_query.group_by(
            store_models.StoreIssueItem.item_id,
            store_models.StoreIssue.kitchen_id
        )

        issued_data = {
            (row.item_id, row.kitchen_id): float(row.total_issued or 0)
            for row in issued_query.all()
        }

        # ============================================
        # 2️⃣ TOTAL USED (Meal Orders)
        # ============================================
        used_query = (
            db.query(
                restaurant_models.MealOrderItem.store_item_id.label("item_id"),
                restaurant_models.MealOrder.kitchen_id.label("kitchen_id"),
                func.sum(restaurant_models.MealOrderItem.store_qty_used).label("total_used")
            )
            .join(
                restaurant_models.MealOrder,
                restaurant_models.MealOrder.id == restaurant_models.MealOrderItem.order_id
            )
            .filter(
                restaurant_models.MealOrder.business_id == business_id
            )
        )

        if filtered_item_ids:
            used_query = used_query.filter(
                restaurant_models.MealOrderItem.store_item_id.in_(filtered_item_ids)
            )

        if kitchen_id:
            used_query = used_query.filter(restaurant_models.MealOrder.kitchen_id == kitchen_id)
        if start_date:
            used_query = used_query.filter(restaurant_models.MealOrder.created_at >= start_date)
        if end_date:
            used_query = used_query.filter(restaurant_models.MealOrder.created_at <= end_date)

        used_query = used_query.group_by(
            restaurant_models.MealOrderItem.store_item_id,
            restaurant_models.MealOrder.kitchen_id
        )

        used_data = {
            (row.item_id, row.kitchen_id): float(row.total_used or 0)
            for row in used_query.all()
        }

        # ============================================
        # 3️⃣ TOTAL ADJUSTED
        # ============================================
        adjusted_query = (
            db.query(
                kitchen_models.KitchenInventoryAdjustment.item_id,
                kitchen_models.KitchenInventoryAdjustment.kitchen_id,
                func.sum(kitchen_models.KitchenInventoryAdjustment.quantity_adjusted).label("total_adjusted")
            )
            .filter(
                kitchen_models.KitchenInventoryAdjustment.business_id == business_id
            )
        )

        if filtered_item_ids:
            adjusted_query = adjusted_query.filter(
                kitchen_models.KitchenInventoryAdjustment.item_id.in_(filtered_item_ids)
            )

        if kitchen_id:
            adjusted_query = adjusted_query.filter(kitchen_models.KitchenInventoryAdjustment.kitchen_id == kitchen_id)
        if start_date:
            adjusted_query = adjusted_query.filter(kitchen_models.KitchenInventoryAdjustment.adjusted_at >= start_date)
        if end_date:
            adjusted_query = adjusted_query.filter(kitchen_models.KitchenInventoryAdjustment.adjusted_at <= end_date)

        adjusted_query = adjusted_query.group_by(
            kitchen_models.KitchenInventoryAdjustment.item_id,
            kitchen_models.KitchenInventoryAdjustment.kitchen_id
        )

        adjusted_data = {
            (row.item_id, row.kitchen_id): float(row.total_adjusted or 0)
            for row in adjusted_query.all()
        }

        # ============================================
        # 4️⃣ MERGE (same as bar)
        # ============================================
        all_keys = set(issued_data.keys()) | set(used_data.keys()) | set(adjusted_data.keys())
        results = []

        for (i_id, k_id) in all_keys:
            if k_id is None:
                continue

            total_issued = issued_data.get((i_id, k_id), 0)
            total_used = used_data.get((i_id, k_id), 0)
            total_adjusted = adjusted_data.get((i_id, k_id), 0)

            balance = total_issued - total_used - total_adjusted

            item = db.query(store_models.StoreItem).filter_by(
                id=i_id,
                business_id=business_id
            ).first()

            if not item:
                continue

            kitchen = db.query(kitchen_models.Kitchen).filter_by(
                id=k_id,
                business_id=business_id
            ).first()

            if not kitchen:
                continue

            if search:
                search_lower = search.lower()
                if search_lower not in item.name.lower() and (
                    not item.category or search_lower not in item.category.name.lower()
                ):
                    continue

            latest_entry = (
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

            unit_price = float(latest_entry.unit_price) if latest_entry else None
            balance_total_amount = round(balance * unit_price, 2) if unit_price else None

            results.append(
                kitchen_schemas.KitchenStockBalance(
                    kitchen_id=k_id,
                    kitchen_name=kitchen.name,
                    item_id=i_id,
                    item_name=item.name,
                    category_name=item.category.name if item.category else None,
                    unit=item.unit,
                    item_type=item.item_type,
                    total_issued=total_issued,
                    total_used=total_used,
                    total_adjusted=total_adjusted,
                    balance=balance,
                    last_unit_price=unit_price,
                    balance_total_amount=balance_total_amount
                )
            )

        results.sort(key=lambda x: (x.kitchen_name.lower(), x.item_name.lower()))
        return results

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve kitchen stock balance: {str(e)}"
        )
