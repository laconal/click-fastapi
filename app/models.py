from datetime import datetime

from sqlalchemy import Column, Integer, BigInteger, Numeric, String, DateTime

from .database import Base


class Order(Base):
    """Your own order / invoice. merchant_trans_id sent to Click == str(Order.id)."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String, default="pending")  # pending | reserved | paid | cancelled
    created_at = Column(DateTime, default=datetime.utcnow)


class ClickTransaction(Base):
    """
    One row per click_trans_id (one payment attempt on Click's side).
    This row's own `id` is what we hand back to Click as merchant_prepare_id,
    and later as merchant_confirm_id.
    """
    __tablename__ = "click_transactions"

    id = Column(Integer, primary_key=True, index=True)
    click_trans_id = Column(BigInteger, unique=True, index=True, nullable=False)
    click_paydoc_id = Column(BigInteger, nullable=True)
    merchant_trans_id = Column(String, index=True, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    state = Column(String, default="created")  # created | prepared | completed | cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
