from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship, declared_attr


class BusinessMixin:

    @declared_attr
    def business_id(cls):
        return Column(
            Integer,
            ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
            index=True
        )

    @declared_attr
    def business(cls):
        return relationship("Business")
