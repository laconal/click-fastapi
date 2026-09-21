"""
Thin async client for calls YOU make to Click (as opposed to the
Prepare/Complete webhooks Click makes to you - see main.py for those).
"""
from decimal import Decimal
from typing import Optional

import httpx

from .config import CLICK_API_BASE_URL, CLICK_SERVICE_ID
from .click_utils import build_merchant_api_auth_header


async def _request(method: str, path: str, json: Optional[dict] = None) -> dict:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Auth": build_merchant_api_auth_header(),
    }
    async with httpx.AsyncClient(base_url=CLICK_API_BASE_URL, timeout=15) as client:
        resp = await client.request(method, path, json=json, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def create_invoice(amount: Decimal, phone_number: str, merchant_trans_id: str) -> dict:
    return await _request("POST", "/invoice/create", json={
        "service_id": CLICK_SERVICE_ID,
        "amount": float(amount),
        "phone_number": phone_number,
        "merchant_trans_id": merchant_trans_id,
    })


async def invoice_status(invoice_id: int) -> dict:
    return await _request("GET", f"/invoice/status/{CLICK_SERVICE_ID}/{invoice_id}")


async def payment_status(payment_id: int) -> dict:
    return await _request("GET", f"/payment/status/{CLICK_SERVICE_ID}/{payment_id}")


async def payment_status_by_mti(merchant_trans_id: str) -> dict:
    return await _request("GET", f"/payment/status_by_mti/{CLICK_SERVICE_ID}/{merchant_trans_id}")


async def reverse_payment(payment_id: int) -> dict:
    """Refund/cancel. Only current-month payments (or prior-month on the 1st), card payments only."""
    return await _request("DELETE", f"/payment/reversal/{CLICK_SERVICE_ID}/{payment_id}")
