# fastapiclick

Demo FastAPI integration with [Click.uz](https://docs.click.uz) covering both
directions of their API:

- **SHOP-API** - the `Prepare` / `Complete` webhooks Click calls on *your*
  server after a user pays on Click's checkout page. See
  [app/main.py](app/main.py).
- **Merchant API** - outbound calls *you* make to Click (payment status,
  reversal). See [app/click_client.py](app/click_client.py).

Signature handling for both (MD5 for SHOP-API, SHA1 `Auth` header for
Merchant API) lives in [app/click_utils.py](app/click_utils.py).

## Local development

```bash
cp .env.example .env   # fill in real values from your Click merchant cabinet
uv run uvicorn app.main:app --reload
```

Test the whole Prepare/Complete flow locally without needing Click's servers:

```bash
uv run python scripts/simulate_click_webhook.py
```

This creates an order, then plays the Prepare and Complete webhooks against
it with correctly-computed signatures. A `CLICK_ERROR_SIGN_FAILED` here means
your local `CLICK_SECRET_KEY` doesn't match what you're testing against.

## Deploying to a VPS (systemd + uv, no Docker)

Assumes a Debian/Ubuntu VPS and a domain already pointed at its IP. Click's
webhooks require a real public HTTPS URL - it cannot call back to `localhost`
or a bare IP, so the domain is not optional.

### 1. System prep

```bash
sudo adduser --system --group --home /opt/fastapiclick fastapiclick
sudo apt update && sudo apt install -y nginx git
curl -LsSf https://astral.sh/uv/install.sh | sh   # as the fastapiclick user, or root
```

`uv` reads `.python-version` (currently `3.14`) and will download that exact
Python build itself - you don't need to install Python system-wide.

### 2. Get the code onto the box

```bash
sudo -u fastapiclick git clone <your-repo-url> /opt/fastapiclick
cd /opt/fastapiclick
sudo -u fastapiclick uv sync --frozen
sudo -u fastapiclick cp .env.example .env
sudo -u fastapiclick $EDITOR .env   # real CLICK_* values from the merchant cabinet
```

Set `CLICK_RETURN_URL` in `.env` to `https://your-domain.com/orders/thank-you`
(or wherever you want the user's browser sent after paying).

For anything beyond a quick demo, point `DATABASE_URL` at Postgres instead of
the default SQLite - SQLite doesn't handle concurrent writers well, which is
why the systemd unit below runs a single worker.

### 3. systemd service

```bash
sudo cp deploy/fastapiclick.service /etc/systemd/system/
```

Edit the `ExecStart` line's `uv` path to match `which uv` for the
`fastapiclick` user (the installer's default is
`~/.local/bin/uv`), then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fastapiclick
sudo systemctl status fastapiclick
journalctl -u fastapiclick -f   # tail logs
```

The app listens on `127.0.0.1:8000` only - it's not exposed directly.

### 4. nginx + TLS

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/fastapiclick
sudo sed -i 's/your-domain.com/YOUR_ACTUAL_DOMAIN/' /etc/nginx/sites-available/fastapiclick
sudo ln -s /etc/nginx/sites-available/fastapiclick /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Certbot rewrites the nginx config in place to add the TLS server block and
the `:80 -> :443` redirect, and sets up auto-renewal.

Lock down the firewall so only nginx is reachable from outside:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 5. Register the webhook URLs with Click

In your Click merchant cabinet, set:

- Prepare URL ("Tasdiqlash manzili"): `https://your-domain.com/payments/click/prepare`
- Complete URL ("Natija manzili"): `https://your-domain.com/payments/click/complete`

## Testing the live deployment

1. **Signature sanity check from your own machine**, pointed at the public
   URL instead of localhost:

   ```bash
   uv run python scripts/simulate_click_webhook.py https://your-domain.com
   ```

   This only proves your server-side signing/logic is correct - Click itself
   never calls this script's endpoints, so it doesn't validate that Click can
   actually reach you.

2. **Real Click test transaction.** Click.uz has no public sandbox; you
   verify against production with a small real payment. Call `POST /orders`
   (or your real checkout flow) to get a `checkout_url`, pay it from a real
   card, and confirm:
   - `journalctl -u fastapiclick -f` shows the Prepare then Complete calls
     arriving from Click's IPs;
   - the order's `status` ends up `paid` in the database;
   - the merchant cabinet's transaction log agrees.

3. **Outbound Merchant API calls** (`GET /payments/click/status/{id}`,
   `POST /payments/click/reverse/{id}`) - exercise these against the
   `click_paydoc_id`/payment id from the test transaction above, since they
   also have no sandbox equivalent.

If Prepare/Complete calls never arrive at all (nothing in the logs), check
first that `https://your-domain.com/payments/click/prepare` is reachable from
outside your own network (e.g. via a phone on mobile data, not VPN'd through
the VPS) and that `ufw`/nginx aren't blocking it.
