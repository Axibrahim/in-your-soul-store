# IN YOUR SOUL

Egyptian streetwear store (est. 2025) — live at **[inyoursoul.store](https://www.inyoursoul.store)**.
Server-rendered **Flask** app with a PostgreSQL database (Supabase), cash-on-delivery
and mobile-wallet checkout, guest checkout, an admin panel, and an installable PWA.

---

## Features

| Area | What it does |
|---|---|
| **Storefront** | Hero + "Latest Hits" swipe carousel, shop with category filter, sorting, search and pagination, product pages with size variants |
| **Cart** | Session cart, size and quantity updates, live item count |
| **Discount codes** | Percent or fixed (EGP) codes with minimum subtotal, max uses and expiry; re-validated at checkout |
| **Checkout** | Saved addresses, delivery fee of 80 EGP (free from 1,500 EGP), payment by **cash on delivery**, **Vodafone Cash** or **InstaPay** |
| **Guest checkout** | Order with just a name and phone number, no account or email needed |
| **Stock safety** | Stock is decremented atomically in the database before the order is created, so two simultaneous checkouts can never oversell a size |
| **Online payment deadline** | Vodafone Cash / InstaPay orders get 2 hours to be paid; unpaid ones are cancelled automatically |
| **Accounts** | Register with email verification, login, forgot / reset password, profile, change password, address book, order history, order tracking |
| **Refunds** | Customers can request a refund within 48 hours of delivery, with item and receipt photos; admins approve or reject |
| **Emails (Resend)** | Verification, password reset, order status updates, refund request and refund status emails, and an email to the admin on every new order |
| **Admin panel** | Dashboard, products (add, edit, activate, deactivate, delete, mobile-friendly edit), categories, orders, refunds, users, discount codes |
| **PWA** | Installable, offline page, iOS splash screens, service worker |

---

## Tech stack

- **Backend:** Flask 3, Flask-SQLAlchemy, Flask-Login, Flask-Bcrypt, Flask-WTF (CSRF), Flask-Limiter, Flask-Caching
- **Database:** PostgreSQL on Supabase in production, SQLite (`freks.db`) when `DATABASE_URL` is not set
- **Storage:** Supabase Storage (bucket `product-images`) for product photos and refund evidence
- **Email:** Resend
- **Images:** Pillow + pillow-heif (iPhone HEIC photos are converted to JPEG on upload)
- **Server:** Gunicorn
- **Frontend:** Jinja templates, vanilla JS and CSS, no inline scripts

---

## Project structure

```
in-your-soul-store/
├── Procfile                    # gunicorn wsgi:app --workers 4 --threads 2 --timeout 60
├── wsgi.py                     # production entrypoint
├── run.py                      # local entrypoint (creates tables + first admin)
├── config.py                   # development / production config
├── seed.py                     # optional demo data (categories, sample products)
├── locustfile.py               # load test
├── generate_pwa_assets.py      # PWA icon / splash generator
├── requirements.txt
├── requirements-dev.txt        # locust
└── app/
    ├── __init__.py             # app factory, security headers, CSP, limiter, cache
    ├── auth_guard.py           # DB-backed session tokens
    ├── password_policy.py      # password rules
    ├── email.py                # Resend emails + signed tokens
    ├── models/__init__.py      # User, Address, Category, Product, ProductVariant,
    │                           # DiscountCode, Order, OrderItem, RefundRequest, RefundImage
    ├── routes/
    │   ├── main.py             # home, shop, product, about, /api/products
    │   ├── auth.py             # login, guest, register, verify, forgot / reset
    │   ├── cart.py             # cart, discounts, checkout
    │   ├── account.py          # profile, addresses, orders, refunds
    │   ├── admin.py            # admin panel
    │   └── pwa.py              # manifest, service worker, offline, icons
    ├── templates/              # base, main/, auth/, account/, admin/, partials/, errors/
    └── static/
        ├── css/                # main.css, latest-swipe.css, pwa.css
        ├── js/                 # main.js, latest-swipe.js, product-form.js,
        │                       # password-policy.js, pwa.js, sw.js
        ├── images/             # logo, icons, splash, backgrounds
        └── videos/             # optional hero.mp4 / latest-hits.mp4
```

---

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root. For local development you only need:

```env
SECRET_KEY=any-long-random-string
```

Without `DATABASE_URL` the app uses a local SQLite file, so no database setup is needed.

```bash
python run.py        # http://127.0.0.1:5000
```

On start, `run.py` creates the tables and, if it does not exist yet, the admin
account `bahz`. Set `ADMIN_BOOTSTRAP_PASSWORD` in `.env` to choose its password;
otherwise a random one is generated and printed once in the terminal.

Optional demo data (categories and sample products):

```bash
python seed.py
```

> `seed.py` also creates a demo admin and a demo user with fixed passwords. Use it
> for local testing only, and never run it against production.

Product photo uploads need Supabase configured (see below). Without it, uploads
fail and are logged.

---

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs sessions and email tokens (**required in production**) |
| `DATABASE_URL` | PostgreSQL URL (**required in production**). `postgres://` is rewritten automatically |
| `FLASK_ENV` | `production` (default for `wsgi.py`) or `development` |
| `BASE_URL` | Public site URL used in email links (default `https://inyoursoul.store`) |
| `SUPABASE_URL`, `SUPABASE_KEY` | Storage for product and refund photos |
| `RESEND_API_KEY` | Email sending |
| `RESEND_FROM_EMAIL` | Sender for account emails |
| `RESEND_ORDERS_FROM_EMAIL` | Sender for order / refund emails |
| `ADMIN_NOTIFY_EMAIL` | Where "new order" alerts are sent |
| `ADMIN_BOOTSTRAP_PASSWORD` | Password for the first admin created by `run.py` |

---

## Orders and payments

1. The customer adds items to the cart (session based) and optionally applies a discount code.
2. At checkout the address is validated (street, building, floor, district and governorate are required) and the payment method must be one of `cod`, `vodafone_cash`, `instapay`.
3. Stock is reduced in one conditional database update; if any size has run out, the order is not created.
4. The order is created with status `pending`, and the admin gets an email.
5. For Vodafone Cash and InstaPay, `payment_deadline` is set 2 hours ahead. Unpaid orders past the deadline are cancelled automatically (checked at most once a minute, when the home page is loaded).
6. The admin moves the order through `pending → confirmed → shipped → delivered` (or `cancelled`). The customer is emailed on each change.
7. When an order becomes `delivered`, the 48-hour refund window starts.

---

## Security

| Control | Where | Detail |
|---|---|---|
| Passwords | `password_policy.py`, Flask-Bcrypt | Min. 10 characters with upper, lower, number and symbol; common passwords and anything containing the username or email are rejected |
| Sessions | `auth_guard.py` | Each login issues a random token; only its SHA-256 hash is stored in the database. A new login revokes old sessions, logout revokes the token, and tokens expire after 7 days without activity |
| Cookies | `config.py` | HTTP-only, SameSite=Lax, Secure in production, 30-day remember-me |
| CSRF | Flask-WTF | Enabled on every form and POST |
| Brute force | Flask-Limiter | Login 5/min, guest checkout 5/hour, register 3/hour, forgot / reset / resend 5/hour, cart add 30/min, discount codes 15/min, checkout 10/min, 1,000/hour global |
| Email tokens | `email.py` | Signed and expiring: verification 1 hour, password reset 30 minutes |
| Headers | `app/__init__.py` | CSP with `script-src 'self'` (no inline JS), `frame-ancestors 'none'`, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, HSTS in production |
| Uploads | `admin.py` | Extension allowlist **and** real image-format check with Pillow before upload; random file names |
| Access control | `admin.py` | Every admin route is `@login_required` plus `@admin_required` |
| Errors | `app/__init__.py` | Friendly 429 page; debug is off in production |

---

## Performance

- Home and shop queries are cached for 30 seconds with Flask-Caching. Only plain data is cached, never live query objects or rendered pages.
- The database pool is capped per Gunicorn worker so the Supabase pooler's connection limit is never exceeded. `prepare_threshold` is disabled for the transaction-mode pooler (port 6543).
- Load test with Locust:

  ```bash
  pip install -r requirements-dev.txt
  locust -f locustfile.py --host http://127.0.0.1:5000
  ```

---

## Deployment

The `Procfile` runs:

```
web: gunicorn wsgi:app --workers 4 --threads 2 --timeout 60
```

Set `SECRET_KEY`, `DATABASE_URL`, `BASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`,
`RESEND_API_KEY`, the two `RESEND_*_FROM_EMAIL` values and `ADMIN_NOTIFY_EMAIL` on the host.
In production the app refuses to start without `SECRET_KEY` and `DATABASE_URL`.
Create the tables once against the production database, and promote your account to
admin (`is_admin = true` on your row in `users`).

> The CSP `img-src` in `app/__init__.py` allows the Supabase project host used for
> product images. If you move to a different Supabase project, update it there.

---

## Brand

Dark, near-black background (`#040804`) with a neon green accent (`#76ff03`),
glitch-style hero type, and a cyber-rain canvas as the fallback when no hero video
is provided. To use a video, drop `hero.mp4` (1920×1080, H.264, under 20 MB) into
`app/static/videos/`. The "Latest Hits" section can use `latest-hits.mp4` and
`images/latest-hits-bg.jpg`.
