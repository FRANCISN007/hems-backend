import pandas as pd
import traceback
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.store import models as store_models


# ------------------- IMPORT STORE ITEMS -------------------
def import_from_excel(
    db: Session,
    file: UploadFile,
    current_user,
    business_id: int | None
):

    # -----------------------------
    # 1️⃣ BUSINESS CHECK
    # -----------------------------
    if "super_admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Only super admin allowed")

    if not business_id:
        raise HTTPException(status_code=400, detail="business_id is required")

    # -----------------------------
    # 2️⃣ READ EXCEL
    # -----------------------------
    try:
        df = pd.read_excel(file.file)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Excel file")

    df.columns = [c.strip().lower() for c in df.columns]

    required_cols = ["name", "unit", "category"]

    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing column: {col}"
            )

    created = 0
    skipped = 0
    errors = []

    # -----------------------------
    # 3️⃣ PROCESS ROWS
    # -----------------------------
    for index, row in df.iterrows():

        try:
            name = str(row.get("name", "")).strip()
            unit = str(row.get("unit", "")).strip()
            category_name = str(row.get("category", "")).strip()

            unit_price = float(row.get("unit_price") or 0)
            selling_price = float(row.get("selling_price") or 0)

            item_type = str(row.get("item_type") or "").strip() or None
            opening_stock = float(row.get("opening_stock") or 0)

            category_id = row.get("category_id")

            # Handle NaN category IDs
            if pd.isna(category_id):
                category_id = None

            # -----------------------------
            # Validate required fields
            # -----------------------------
            if not name or not unit:

                skipped += 1

                errors.append({
                    "row": index + 2,
                    "item": name,
                    "reason": "Missing item name or unit"
                })

                continue

            # -----------------------------
            # Resolve Category
            # -----------------------------
            category = None

            if category_id is not None:
                category = db.query(store_models.StoreCategory).filter(
                    store_models.StoreCategory.id == int(category_id)
                ).first()

            if not category and category_name:
                category = db.query(store_models.StoreCategory).filter(
                    store_models.StoreCategory.name == category_name
                ).first()

            if not category:

                skipped += 1

                errors.append({
                    "row": index + 2,
                    "item": name,
                    "reason": f"Category '{category_name}' not found"
                })

                continue

            # -----------------------------
            # Duplicate Check
            # -----------------------------
            exists = db.query(store_models.StoreItem).filter(
                store_models.StoreItem.name == name,
                store_models.StoreItem.category_id == category.id,
                store_models.StoreItem.business_id == business_id
            ).first()

            if exists:

                skipped += 1

                errors.append({
                    "row": index + 2,
                    "item": name,
                    "reason": "Item already exists"
                })

                continue

            # -----------------------------
            # Create Item
            # -----------------------------
            item = store_models.StoreItem(
                name=name,
                unit=unit,
                category_id=category.id,
                unit_price=unit_price,
                selling_price=selling_price,
                item_type=item_type,
                business_id=business_id,
            )

            db.add(item)
            db.flush()

            inventory = store_models.StoreInventory(
                item_id=item.id,
                opening_quantity=opening_stock,
                quantity=opening_stock,
                business_id=business_id
            )

            db.add(inventory)

            created += 1

        except Exception as e:

            traceback.print_exc()

            skipped += 1

            errors.append({
                "row": index + 2,
                "item": str(row.get("name", "")),
                "reason": str(e)
            })

            continue

    # -----------------------------
    # 4️⃣ COMMIT
    # -----------------------------
    try:
        db.commit()

    except IntegrityError as e:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=f"Import failed: {str(e)}"
        )

    # -----------------------------
    # 5️⃣ RETURN RESULT
    # -----------------------------
    return {
        "message": "Store items import completed",
        "created": created,
        "skipped": skipped,
        "errors": errors
    }