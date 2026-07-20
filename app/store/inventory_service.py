from sqlalchemy.orm import Session
from sqlalchemy import func

from app.store import models as store_models
from app.bar import models as bar_models


from sqlalchemy import func


def calculate_available_stock(
    db: Session,
    business_id: int,
    item_id: int,
):
    """
    Calculate the current available stock.

    Formula:

        Opening Stock
      + Remaining Purchase Stock
      - Net Adjustments

    Adjustment sign convention:

        +5 = remove 5
        -5 = add 5
    """

    # -----------------------------------------
    # Remaining Opening Stock
    # -----------------------------------------
    opening_stock = (
        db.query(
            func.coalesce(
                func.sum(store_models.StoreInventory.quantity),
                0
            )
        )
        .filter(
            store_models.StoreInventory.business_id == business_id,
            store_models.StoreInventory.item_id == item_id,
        )
        .scalar()
    )

    # -----------------------------------------
    # Remaining Purchase Stock
    # -----------------------------------------
    purchased_stock = (
        db.query(
            func.coalesce(
                func.sum(store_models.StoreStockEntry.quantity),
                0
            )
        )
        .filter(
            store_models.StoreStockEntry.business_id == business_id,
            store_models.StoreStockEntry.item_id == item_id,
        )
        .scalar()
    )

    # -----------------------------------------
    # Net Adjustments
    #
    # Positive values = stock removed
    # Negative values = stock added
    # -----------------------------------------
    adjustment_total = (
        db.query(
            func.coalesce(
                func.sum(store_models.StoreInventoryAdjustment.quantity_adjusted),
                0
            )
        )
        .filter(
            store_models.StoreInventoryAdjustment.business_id == business_id,
            store_models.StoreInventoryAdjustment.item_id == item_id,
        )
        .scalar()
    )

    available = (
        opening_stock
        + purchased_stock
        - adjustment_total
    )

    return max(available, 0)




def deduct_fifo_stock(
    db: Session,
    business_id: int,
    item_id: int,
    quantity: float,
):
    """
    Deduct inventory using FIFO.

    Order:
    1. Purchase batches
    2. Positive adjustment stock
    3. Opening stock
    """

    remaining = float(quantity)

    # ---------------------------------------------------
    # 1. Deduct Purchase Stock (FIFO)
    # ---------------------------------------------------
    purchases = (
        db.query(store_models.StoreStockEntry)
        .filter(
            store_models.StoreStockEntry.business_id == business_id,
            store_models.StoreStockEntry.item_id == item_id,
            store_models.StoreStockEntry.quantity > 0,
        )
        .order_by(
            store_models.StoreStockEntry.purchase_date.asc(),
            store_models.StoreStockEntry.id.asc(),
        )
        .all()
    )

    for purchase in purchases:

        if remaining <= 0:
            break

        deduct = min(float(purchase.quantity), remaining)

        purchase.quantity -= deduct
        remaining -= deduct

        db.add(purchase)





    # ---------------------------------------------------
    # 2. Deduct Adjustment Stock (FIFO)
    # ---------------------------------------------------
    if remaining > 0:

        adjustments = (
            db.query(store_models.StoreInventoryAdjustment)
            .filter(
                store_models.StoreInventoryAdjustment.business_id == business_id,
                store_models.StoreInventoryAdjustment.item_id == item_id,
                store_models.StoreInventoryAdjustment.remaining_quantity > 0,
            )
            .order_by(
                store_models.StoreInventoryAdjustment.adjusted_at.asc(),
                store_models.StoreInventoryAdjustment.id.asc(),
            )
            .all()
        )

        for adj in adjustments:

            if remaining <= 0:
                break

            deduct = min(float(adj.remaining_quantity), remaining)

            adj.remaining_quantity -= deduct
            remaining -= deduct

            db.add(adj)

    # ---------------------------------------------------
    # 3. Deduct Opening Stock
    # ---------------------------------------------------
    if remaining > 0:

        openings = (
            db.query(store_models.StoreInventory)
            .filter(
                store_models.StoreInventory.business_id == business_id,
                store_models.StoreInventory.item_id == item_id,
                store_models.StoreInventory.quantity > 0,
            )
            .order_by(store_models.StoreInventory.id.asc())
            .all()
        )

        for opening in openings:

            if remaining <= 0:
                break

            deduct = min(float(opening.quantity), remaining)

            opening.quantity -= deduct
            remaining -= deduct

            db.add(opening)


    

    # ---------------------------------------------------
    # Safety Check
    # ---------------------------------------------------
    if remaining > 0:
        raise ValueError(
            f"Unable to deduct {quantity}. "
            f"{remaining} units could not be deducted."
        )

        
def restore_fifo_stock(
    db: Session,
    business_id: int,
    item_id: int,
    quantity: float,
):
    """
    Restore stock in the reverse order:
    1. Negative adjustments
    2. Purchases
    3. Opening stock
    """

    remaining = quantity

    # -----------------------------------
    # Restore adjustment stock
    # -----------------------------------
    adjustments = (
        db.query(store_models.StoreInventoryAdjustment)
        .filter(
            store_models.StoreInventoryAdjustment.business_id == business_id,
            store_models.StoreInventoryAdjustment.item_id == item_id,
            store_models.StoreInventoryAdjustment.quantity_adjusted < 0,
        )
        .order_by(
            store_models.StoreInventoryAdjustment.adjusted_at.asc(),
            store_models.StoreInventoryAdjustment.id.asc(),
        )
        .all()
    )

    for adj in adjustments:

        if remaining <= 0:
            break

        original_added = abs(adj.quantity_adjusted)

        available_space = original_added - adj.remaining_quantity

        if available_space <= 0:
            continue

        restore = min(available_space, remaining)

        adj.remaining_quantity += restore
        remaining -= restore

    # -----------------------------------
    # Restore purchase stock
    # -----------------------------------
    if remaining > 0:

        purchases = (
            db.query(store_models.StoreStockEntry)
            .filter(
                store_models.StoreStockEntry.business_id == business_id,
                store_models.StoreStockEntry.item_id == item_id,
            )
            .order_by(
                store_models.StoreStockEntry.purchase_date.asc(),
                store_models.StoreStockEntry.id.asc(),
            )
            .all()
        )

        for purchase in purchases:

            if remaining <= 0:
                break

            purchase.quantity += remaining
            remaining = 0

    # -----------------------------------
    # Restore opening stock
    # -----------------------------------
    if remaining > 0:

        inventories = (
            db.query(store_models.StoreInventory)
            .filter(
                store_models.StoreInventory.business_id == business_id,
                store_models.StoreInventory.item_id == item_id,
            )
            .all()
        )

        for inventory in inventories:

            if remaining <= 0:
                break

            inventory.quantity += remaining
            remaining = 0


def increase_bar_inventory(
    db: Session,
    business_id: int,
    bar_id: int,
    item,
    quantity: float,
):
    """
    Increase bar inventory after an issue.
    """

    bar_inventory = (
        db.query(bar_models.BarInventory)
        .filter(
            bar_models.BarInventory.business_id == business_id,
            bar_models.BarInventory.bar_id == bar_id,
            bar_models.BarInventory.item_id == item.id
        )
        .first()
    )

    if bar_inventory:

        bar_inventory.quantity += quantity

    else:

        db.add(
            bar_models.BarInventory(
                business_id=business_id,
                bar_id=bar_id,
                item_id=item.id,
                quantity=quantity,
                selling_price=item.selling_price
            )
        )


def reset_bar_inventory(
    db: Session,
    business_id: int,
):
    """
    Remove every quantity from every bar.

    It will be rebuilt from StoreIssue afterwards.
    """

    db.query(bar_models.BarInventory).filter(
        bar_models.BarInventory.business_id == business_id
    ).delete()




def rebuild_bar_inventory(
    db: Session,
    business_id: int,
):
    """
    Rebuild bar inventory from StoreIssue history.

    Store adjustments do NOT affect bar inventory.
    Only issues from the store to the bar are replayed.
    """

    # -----------------------------------------
    # Load all store items
    # -----------------------------------------
    items = {
        item.id: item
        for item in (
            db.query(store_models.StoreItem)
            .filter(
                store_models.StoreItem.business_id == business_id
            )
            .all()
        )
    }

    # -----------------------------------------
    # Load every issue sent to bars
    # -----------------------------------------
    issues = (
        db.query(store_models.StoreIssue)
        .filter(
            store_models.StoreIssue.business_id == business_id,
            store_models.StoreIssue.issue_to == "bar",
        )
        .order_by(
            store_models.StoreIssue.issue_date.asc(),
            store_models.StoreIssue.id.asc(),
        )
        .all()
    )

    # -----------------------------------------
    # Replay issues
    # -----------------------------------------
    for issue in issues:

        # Skip invalid issues
        if not issue.bar_id:
            continue

        for issue_item in issue.issue_items:

            item = items.get(issue_item.item_id)

            if item is None:
                continue

            increase_bar_inventory(
                db=db,
                business_id=business_id,
                bar_id=issue.bar_id,
                item=item,
                quantity=issue_item.quantity,
            )






def reset_purchase_inventory(
    db: Session,
    business_id: int,
):
    """
    Restore every purchase batch to its original quantity.
    """

    purchases = (
        db.query(store_models.StoreStockEntry)
        .filter(
            store_models.StoreStockEntry.business_id == business_id
        )
        .all()
    )

    for purchase in purchases:
        purchase.quantity = purchase.original_quantity



def reset_opening_inventory(
    db: Session,
    business_id: int,
):
    """
    Restore every opening stock item.
    """

    inventories = (
        db.query(store_models.StoreInventory)
        .filter(
            store_models.StoreInventory.business_id == business_id
        )
        .all()
    )

    for inv in inventories:
        inv.quantity = inv.opening_quantity


def replay_store_adjustments(
    db: Session,
    business_id: int,
):
    """
    Replay every stock adjustment.

    Positive adjustment (+)
        -> Remove stock using FIFO.

    Negative adjustment (-)
        -> Restore the adjustment's own remaining quantity.
        It is NOT converted into a purchase.
    """

    adjustments = (
        db.query(store_models.StoreInventoryAdjustment)
        .filter(
            store_models.StoreInventoryAdjustment.business_id == business_id
        )
        .order_by(
            store_models.StoreInventoryAdjustment.adjusted_at.asc(),
            store_models.StoreInventoryAdjustment.id.asc(),
        )
        .all()
    )

    for adj in adjustments:

        qty = adj.quantity_adjusted

        # -------------------------
        # REMOVE STOCK
        # -------------------------
        if qty > 0:

            deduct_fifo_stock(
                db=db,
                business_id=business_id,
                item_id=adj.item_id,
                quantity=qty,
            )

            adj.remaining_quantity = 0

        # -------------------------
        # ADD STOCK
        # -------------------------
        elif qty < 0:

            adj.remaining_quantity = abs(qty)

        else:

            adj.remaining_quantity = 0





def replay_store_issues(
    db: Session,
    business_id: int,
):
    """
    Replay every issue in chronological order.

    This reproduces the exact stock balances as if
    every issue happened again.
    """

    issues = (
        db.query(store_models.StoreIssue)
        .filter(
            store_models.StoreIssue.business_id == business_id
        )
        .order_by(
            store_models.StoreIssue.issue_date.asc(),
            store_models.StoreIssue.id.asc()
        )
        .all()
    )

    for issue in issues:

        for issue_item in issue.issue_items:

            deduct_fifo_stock(
                db=db,
                business_id=business_id,
                item_id=issue_item.item_id,
                quantity=issue_item.quantity,
            )




def rebuild_store_inventory(
    db: Session,
    business_id: int,
):
    """
    Completely rebuild store inventory.

    Order matters:

    1. Restore purchases.
    2. Restore opening stock.
    3. Replay stock adjustments.
    4. Replay issues (FIFO).
    """

    reset_purchase_inventory(
        db,
        business_id,
    )

    reset_opening_inventory(
        db,
        business_id,
    )

    replay_store_adjustments(
        db,
        business_id,
    )

    replay_store_issues(
        db,
        business_id,
    )





def rebuild_everything(
    db: Session,
    business_id: int,
):
    """
    Complete inventory rebuild.

    Safe after any
    UPDATE
    DELETE
    IMPORT
    ADJUSTMENT
    """

    rebuild_store_inventory(
        db,
        business_id,
    )

    reset_bar_inventory(
        db,
        business_id,
    )

    rebuild_bar_inventory(
        db,
        business_id,
    )