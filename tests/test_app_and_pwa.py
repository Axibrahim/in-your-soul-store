import pytest
from werkzeug.exceptions import TooManyRequests

from app import create_app, db


# ---------- PWA ----------

def test_manifest_content(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.mimetype == "application/manifest+json"
    assert "max-age=3600" in resp.headers["Cache-Control"]
    data = resp.get_json()
    assert data["name"] == "IN YOUR SOUL"
    assert data["display"] == "standalone"
    assert len(data["icons"]) == 4
    assert [s["url"] for s in data["shortcuts"]] == ["/shop", "/cart/", "/account/"]


def test_service_worker_headers(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.mimetype == "text/javascript"
    assert resp.headers["Service-Worker-Allowed"] == "/"
    assert resp.headers["Cache-Control"] == "no-cache"


@pytest.mark.parametrize("path", [
    "/offline", "/favicon.ico", "/apple-touch-icon.png", "/apple-touch-icon-precomposed.png",
])
def test_pwa_assets_are_served(client, path):
    assert client.get(path).status_code == 200


# ---------- headers and SEO plumbing ----------

def test_security_headers_including_hsts(client):
    resp = client.get("/about")
    assert resp.headers["Strict-Transport-Security"].startswith("max-age=")
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]


def test_private_pages_are_marked_noindex_and_public_ones_are_not(client):
    assert client.get("/auth/login").headers["X-Robots-Tag"] == "noindex, nofollow"
    assert client.get("/cart/").headers["X-Robots-Tag"] == "noindex, nofollow"
    assert "X-Robots-Tag" not in client.get("/shop").headers


def test_unknown_page_is_404(client):
    assert client.get("/this-page-does-not-exist").status_code == 404


# ---------- error pages ----------

def test_429_page_renders(app, client):
    @app.route("/_force429")
    def force_429():
        raise TooManyRequests()

    assert client.get("/_force429").status_code == 429


# ---------- production safety checks ----------

def test_production_refuses_to_start_without_secrets(monkeypatch):
    from config import ProductionConfig

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")

    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "some-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app("production")


# ---------- rate limiting behind Railway's proxy (verifies the ProxyFix change) ----------

@pytest.fixture()
def limited_app(monkeypatch):
    from config import TestingConfig

    monkeypatch.setattr(TestingConfig, "RATELIMIT_ENABLED", True)
    app = create_app("testing")
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def test_rate_limits_are_per_visitor_not_shared_across_the_proxy(limited_app):
    client = limited_app.test_client()
    attempt = {"email": "nobody@example.com", "password": "wrong"}

    def login_as(visitor_ip):
        return client.post("/auth/login", data=attempt, headers={"X-Forwarded-For": visitor_ip})

    for _ in range(5):
        assert login_as("1.1.1.1").status_code == 200   # 5 attempts per minute are allowed
    assert login_as("1.1.1.1").status_code == 429       # the 6th from the same visitor is blocked
    assert login_as("2.2.2.2").status_code == 200       # a different visitor is not affected