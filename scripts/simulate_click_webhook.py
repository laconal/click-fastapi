"""
End-to-end local test for the Click SHOP-API webhook flow, without
needing Click's servers.

Creates an order, then plays the Prepare (action=0) and Complete
(action=1) webhooks against it exactly as Click would call them -
computing the sign_string the same way click_utils does, so a
CLICK_ERROR_SIGN_FAILED here means your CLICK_SECRET_KEY (or the
config it's read from) doesn't match what's in the merchant cabinet.

Usage:
    uv run python scripts/simulate_click_webhook.py [base_url]

    base_url defaults to http://127.0.0.1:8000. Point it at your
    public https://your-domain.com to test the deployed VPS instead.
"""
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.click_utils import make_prepare_sign, make_complete_sign
from app.config import CLICK_SERVICE_ID


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    amount = "1000.00"

    with httpx.Client(base_url=base_url, timeout=15) as client:
        print(f"-> creating order for {amount}")
        resp = client.post("/orders", params={"amount": amount})
        resp.raise_for_status()
        order = resp.json()
        order_id = str(order["order_id"])
        print(f"   order_id={order_id} checkout_url={order['checkout_url']}")

        click_trans_id = str(int(time.time()))  # fake, unique enough for a manual test
        service_id = str(CLICK_SERVICE_ID)
        sign_time = time.strftime("%Y-%m-%d %H:%M:%S")

        # --- Prepare (action=0) ---
        prepare_sign = make_prepare_sign(click_trans_id, service_id, order_id, amount, "0", sign_time)
        print("\n-> POST /payments/click/prepare")
        resp = client.post("/payments/click/prepare", data={
            "click_trans_id": click_trans_id,
            "service_id": service_id,
            "click_paydoc_id": click_trans_id,
            "merchant_trans_id": order_id,
            "amount": amount,
            "action": "0",
            "sign_time": sign_time,
            "sign_string": prepare_sign,
        })
        print(f"   {resp.status_code} {resp.json()}")
        prepare_json = resp.json()
        if prepare_json.get("error") != 0:
            print("Prepare failed, stopping.")
            return
        merchant_prepare_id = str(prepare_json["merchant_prepare_id"])

        # --- Complete (action=1) ---
        complete_sign = make_complete_sign(
            click_trans_id, service_id, order_id, merchant_prepare_id, amount, "1", sign_time
        )
        print("\n-> POST /payments/click/complete")
        resp = client.post("/payments/click/complete", data={
            "click_trans_id": click_trans_id,
            "service_id": service_id,
            "click_paydoc_id": click_trans_id,
            "merchant_trans_id": order_id,
            "merchant_prepare_id": merchant_prepare_id,
            "amount": amount,
            "action": "1",
            "sign_time": sign_time,
            "sign_string": complete_sign,
        })
        print(f"   {resp.status_code} {resp.json()}")


if __name__ == "__main__":
    main()
