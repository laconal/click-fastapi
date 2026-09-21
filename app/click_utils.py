"""
Two completely different signature schemes:

1. SHOP-API (Prepare/Complete webhooks Click sends you) -> MD5, built from
   the exact form fields Click sent, as strings, concatenated in order.

2. Merchant API (requests you send to Click) -> the `Auth` header, built
   from sha1(timestamp + secret_key).

Signature mismatches are almost always caused by re-formatting numbers
(e.g. "1000" vs "1000.00" vs 1000.0) before hashing. Always hash the raw
string values exactly as received / exactly as you're about to send them.
"""
import hashlib
import time

from .config import CLICK_SECRET_KEY, CLICK_MERCHANT_USER_ID


def make_prepare_sign(click_trans_id: str, service_id: str, merchant_trans_id: str,
                       amount: str, action: str, sign_time: str) -> str:
    raw = f"{click_trans_id}{service_id}{CLICK_SECRET_KEY}{merchant_trans_id}{amount}{action}{sign_time}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_complete_sign(click_trans_id: str, service_id: str, merchant_trans_id: str,
                        merchant_prepare_id: str, amount: str, action: str, sign_time: str) -> str:
    raw = (
        f"{click_trans_id}{service_id}{CLICK_SECRET_KEY}{merchant_trans_id}"
        f"{merchant_prepare_id}{amount}{action}{sign_time}"
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_merchant_api_auth_header() -> str:
    """Auth header for OUTGOING calls to Click's Merchant API."""
    timestamp = str(int(time.time()))
    digest = hashlib.sha1(f"{timestamp}{CLICK_SECRET_KEY}".encode("utf-8")).hexdigest()
    return f"{CLICK_MERCHANT_USER_ID}:{digest}:{timestamp}"
