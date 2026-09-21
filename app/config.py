"""
All Click credentials come from your Click merchant cabinet.
NEVER hardcode secret_key - load it from the environment.
"""
import os

CLICK_SERVICE_ID = int(os.environ.get("CLICK_SERVICE_ID", "0"))
CLICK_MERCHANT_ID = int(os.environ.get("CLICK_MERCHANT_ID", "0"))
CLICK_MERCHANT_USER_ID = int(os.environ.get("CLICK_MERCHANT_USER_ID", "0"))
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "")

# Where Click redirects the user's browser after they finish paying.
# Server-to-server confirmation still happens via the prepare/complete webhooks below -
# this only affects what the user's browser sees.
CLICK_RETURN_URL = os.environ.get("CLICK_RETURN_URL", "https://yourdomain.com/orders/thank-you")

# Outbound Merchant API (you -> Click)
CLICK_API_BASE_URL = "https://api.click.uz/v2/merchant"

# Checkout page you redirect the user to (Click -> you happens later, via webhooks)
CLICK_CHECKOUT_URL = "https://my.click.uz/services/pay"

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./click_demo.db")
