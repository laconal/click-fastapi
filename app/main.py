from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Depends
from sqlalchemy.orm import Session

from .config import CLICK_SERVICE_ID, CLICK_MERCHANT_ID, CLICK_CHECKOUT_URL, CLICK_RETURN_URL
from .database import Base, engine, get_db
from .models import Order, ClickTransaction
from .click_utils import make_prepare_sign, make_complete_sign
from . import click_client

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Click Merchant Integration Demo")

# Standard Click SHOP-API error codes used across integrations.
# Verify the exact text against your merchant cabinet docs; the numeric
# codes below are the ones Click's own systems key off of.
CLICK_ERROR_SUCCESS = 0
CLICK_ERROR_SIGN_FAILED = -1
CLICK_ERROR_AMOUNT = -2
CLICK_ERROR_ACTION_NOT_FOUND = -3
CLICK_ERROR_ALREADY_PAID = -4
CLICK_ERROR_ORDER_NOT_FOUND = -5
CLICK_ERROR_TRANSACTION_NOT_FOUND = -6
CLICK_ERROR_FAILED_TO_UPDATE = -7
CLICK_ERROR_BAD_REQUEST = -8
CLICK_ERROR_TRANSACTION_CANCELLED = -9


# ---------------------------------------------------------------------------
# 1. Your own endpoint: create an order, hand the user a Click checkout link
# ---------------------------------------------------------------------------

@app.post("/orders")
def create_order(amount: Decimal, db: Session = Depends(get_db)):
    order = Order(amount=amount, status="pending")
    db.add(order)
    db.commit()
    db.refresh(order)

    checkout_url = CLICK_CHECKOUT_URL + "?" + urlencode({
        "service_id": CLICK_SERVICE_ID,
        "merchant_id": CLICK_MERCHANT_ID,
        "amount": str(order.amount),
        "transaction_param": order.id,  # this is what Click will send back as merchant_trans_id
        "return_url": CLICK_RETURN_URL,
    })

    return {"order_id": order.id, "checkout_url": checkout_url}


# ---------------------------------------------------------------------------
# 2. Prepare webhook - Click -> you, action = 0
#    Register this exact path as your "Tasdiqlash manzili" / Prepare URL.
# ---------------------------------------------------------------------------

@app.post("/payments/click/prepare")
def click_prepare(
    click_trans_id: str = Form(...),
    service_id: str = Form(...),
    click_paydoc_id: str = Form(...),
    merchant_trans_id: str = Form(...),
    amount: str = Form(...),
    action: str = Form(...),
    sign_time: str = Form(...),
    sign_string: str = Form(...),
    error: str = Form("0"),
    error_note: str = Form(""),
    db: Session = Depends(get_db),
):
    def resp(merchant_prepare_id, err, note):
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": merchant_prepare_id,
            "error": err,
            "error_note": note,
        }

    # --- signature check first, always ---
    expected_sign = make_prepare_sign(click_trans_id, service_id, merchant_trans_id, amount, action, sign_time)
    if expected_sign != sign_string:
        return resp(0, CLICK_ERROR_SIGN_FAILED, "SIGN CHECK FAILED!")

    if int(service_id) != CLICK_SERVICE_ID:
        return resp(0, CLICK_ERROR_BAD_REQUEST, "Wrong service_id")

    order = db.query(Order).filter(Order.id == _safe_int(merchant_trans_id)).first()
    if not order:
        return resp(0, CLICK_ERROR_ORDER_NOT_FOUND, "Order not found")

    try:
        if Decimal(amount) != Decimal(str(order.amount)):
            return resp(0, CLICK_ERROR_AMOUNT, "Incorrect amount")
    except InvalidOperation:
        return resp(0, CLICK_ERROR_AMOUNT, "Incorrect amount")

    # --- idempotency: Click may retry the same click_trans_id ---
    existing = db.query(ClickTransaction).filter(ClickTransaction.click_trans_id == int(click_trans_id)).first()
    if existing:
        if existing.state == "cancelled":
            return resp(0, CLICK_ERROR_TRANSACTION_CANCELLED, "Transaction cancelled")
        return resp(existing.id, CLICK_ERROR_SUCCESS, "Success")

    if order.status == "paid":
        return resp(0, CLICK_ERROR_ALREADY_PAID, "Already paid")

    tx = ClickTransaction(
        click_trans_id=int(click_trans_id),
        click_paydoc_id=int(click_paydoc_id),
        merchant_trans_id=merchant_trans_id,
        amount=Decimal(amount),
        state="prepared",
    )
    db.add(tx)
    order.status = "reserved"  # e.g. hold stock / seat / slot here
    db.commit()
    db.refresh(tx)

    return resp(tx.id, CLICK_ERROR_SUCCESS, "Success")


# ---------------------------------------------------------------------------
# 3. Complete webhook - Click -> you, action = 1
#    Register this exact path as your "Natija manzili" / Complete URL.
# ---------------------------------------------------------------------------

@app.post("/payments/click/complete")
def click_complete(
    click_trans_id: str = Form(...),
    service_id: str = Form(...),
    click_paydoc_id: str = Form(...),
    merchant_trans_id: str = Form(...),
    merchant_prepare_id: str = Form(...),
    amount: str = Form(...),
    action: str = Form(...),
    sign_time: str = Form(...),
    sign_string: str = Form(...),
    error: str = Form("0"),
    error_note: str = Form(""),
    db: Session = Depends(get_db),
):
    def resp(merchant_confirm_id, err, note):
        return {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": merchant_confirm_id,
            "error": err,
            "error_note": note,
        }

    expected_sign = make_complete_sign(
        click_trans_id, service_id, merchant_trans_id, merchant_prepare_id, amount, action, sign_time
    )
    if expected_sign != sign_string:
        return resp(None, CLICK_ERROR_SIGN_FAILED, "SIGN CHECK FAILED!")

    tx = db.query(ClickTransaction).filter(ClickTransaction.click_trans_id == int(click_trans_id)).first()
    if not tx or tx.id != _safe_int(merchant_prepare_id):
        return resp(None, CLICK_ERROR_TRANSACTION_NOT_FOUND, "Transaction not found")

    if tx.state == "completed":
        # Already processed - never re-run fulfilment for a duplicate Complete call.
        return resp(tx.id, CLICK_ERROR_ALREADY_PAID, "Already paid")

    order = db.query(Order).filter(Order.id == _safe_int(merchant_trans_id)).first()
    if not order:
        return resp(tx.id, CLICK_ERROR_ORDER_NOT_FOUND, "Order not found")

    if int(error) < 0:
        # Click itself failed/cancelled the charge on their end -> release your reservation.
        tx.state = "cancelled"
        order.status = "cancelled"
        db.commit()
        return resp(tx.id, CLICK_ERROR_TRANSACTION_CANCELLED, "Transaction cancelled")

    # Funds were actually captured by Click.
    tx.state = "completed"
    order.status = "paid"
    db.commit()

    # TODO: fulfil the order here - grant access, ship goods, send confirmation email, etc.
    # Keep this fast; do slow work (emails, etc.) in a background task/queue.

    return resp(tx.id, CLICK_ERROR_SUCCESS, "Success")


def _safe_int(value: str):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 4. Example outbound Merchant API usage (you -> Click)
# ---------------------------------------------------------------------------

@app.get("/payments/click/status/{payment_id}")
async def get_click_payment_status(payment_id: int):
    return await click_client.payment_status(payment_id)


@app.post("/payments/click/reverse/{payment_id}")
async def reverse_click_payment(payment_id: int):
    return await click_client.reverse_payment(payment_id)
