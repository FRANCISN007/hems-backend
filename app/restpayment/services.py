# app/restpayment/services.py
from sqlalchemy.orm import Session
from app.restaurant.models import RestaurantSale

def update_sale_status(sale: RestaurantSale, db: Session):
    total_paid = sum(p.amount_paid for p in sale.payments)

    if total_paid >= sale.total_amount:
        sale.status = "paid"
    elif total_paid > 0:
        sale.status = "partial"
    else:
        sale.status = "open"

    db.commit()
    db.refresh(sale)
