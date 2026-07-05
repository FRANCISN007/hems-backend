from sqlalchemy.orm import Session
from sqlalchemy import func

from app.store import models as store_models
from app.bar import models as bar_models


def calculate_available_stock(
    db: Session,
    business_id: int,
    item_id: int,
):
    """
    Current available stock.

    Since StoreStockEntry.quantity and StoreInventory.quantity
    are already reduced whenever items are issued,
    we simply sum the remaining balances.
    """

    opening_stock = (
        db.query(
            func.coalesce(
                func.sum(store_models.StoreInventory.quantity),
                0
            )
        )
        .filter(
            store_models.StoreInventory.business_id == business_id,
            store_models.StoreInventory.item_id == item_id
        )
        .scalar()
    )

    purchased_stock = (
        db.query(
            func.coalesce(
                func.sum(store_models.StoreStockEntry.quantity),
                0
            )
        )
        .filter(
            store_models.StoreStockEntry.business_id == business_id,
            store_models.StoreStockEntry.item_id == item_id
        )
        .scalar()
    )

    return opening_stock + purchased_stock



def deduct_fifo_stock(
    db: Session,
    business_id: int,
    item_id: int,
    quantity: float,
):
    """
    Deduct inventory using FIFO.

    Purchases first.

    Opening stock second.
    """

    remaining = quantity

    stock_entries = (
        db.query(store_models.StoreStockEntry)
        .filter(
            store_models.StoreStockEntry.business_id == business_id,
            store_models.StoreStockEntry.item_id == item_id,
            store_models.StoreStockEntry.quantity > 0
        )
        .order_by(
            store_models.StoreStockEntry.purchase_date.asc(),
            store_models.StoreStockEntry.id.asc()
        )
        .all()
    )

    for entry in stock_entries:

        if remaining <= 0:
            break

        if entry.quantity >= remaining:

            entry.quantity -= remaining
            remaining = 0

        else:

            remaining -= entry.quantity
            entry.quantity = 0

    if remaining > 0:

        inventory = (
            db.query(store_models.StoreInventory)
            .filter(
                store_models.StoreInventory.business_id == business_id,
                store_models.StoreInventory.item_id == item_id
            )
            .first()
        )

        if inventory:

            inventory.quantity -= remaining

            if inventory.quantity < 0:
                inventory.quantity = 0




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
    Rebuild every bar inventory from StoreIssue history.
    """

    # Load all items once
    items = {
        item.id: item
        for item in db.query(store_models.StoreItem)
        .filter(store_models.StoreItem.business_id == business_id)
        .all()
    }

    issues = (
        db.query(store_models.StoreIssue)
        .filter(
            store_models.StoreIssue.business_id == business_id,
            store_models.StoreIssue.issue_to == "bar"
        )
        .order_by(
            store_models.StoreIssue.issue_date.asc(),
            store_models.StoreIssue.id.asc()
        )
        .all()
    )

    for issue in issues:

        for issue_item in issue.issue_items:

            item = items.get(issue_item.item_id)

            if not item:
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
    Completely rebuild store inventory from source data.
    """

    reset_purchase_inventory(
        db,
        business_id,
    )

    reset_opening_inventory(
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