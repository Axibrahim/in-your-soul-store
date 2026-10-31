import pytest

from app import db
from app.email import generate_reset_token, generate_verify_token
from app.models import User

NEW_USER = {
    "username": "newuser", "email": "new@example.com", "phone": "01000000005",
    "password": "Str0ng!Passw0rd", "confirm_password": "Str0ng!Passw0rd",
    "first_name": "New", "last_name": "User",
}
NEW_PASSWORD = "R3set!Strong#Pw77"


@pytest.fixture(autouse=True)
def no_real_emails(monkeypatch):
    sent = {"verify": [], "reset": []}
    monkeypatch.setattr("app.routes.auth.send_verification_email",
                        lambda *a, **k: sent["verify"].append(a) or True)
    monkeypatch.setattr("app.routes.auth.send_reset_email",
                        lambda *a, **k: sent["reset"].append(a) or True)
    return sent


def user_count(app):
    with app.app_context():
        return User.query.count()


# ---------- register ----------

def test_register_creates_unverified_user_and_sends_email(app, client, no_real_emails):
    resp = client.post("/auth/register", data=NEW_USER)
    assert resp.status_code == 302
    assert "/auth/check-email" in resp.headers["Location"]
    with app.app_context():
        assert User.query.filter_by(email="new@example.com").one().email_verified is False
    assert len(no_real_emails["verify"]) == 1


@pytest.mark.parametrize("override", [
    {"password": "weak", "confirm_password": "weak"},
    {"confirm_password": "Different!Passw0rd1"},
    {"phone": "abc"},
    {"email": "not-an-email"},
    {"first_name": ""},
])
def test_register_rejects_bad_input(app, client, override):
    resp = client.post("/auth/register", data={**NEW_USER, **override})
    assert resp.status_code == 200
    with app.app_context():
        assert User.query.filter_by(username="newuser").count() == 0


def test_register_rejects_duplicate_email_and_username(app, client, seeded):
    before = user_count(app)
    assert client.post("/auth/register", data={**NEW_USER, "email": seeded["email"]}).status_code == 200
    assert client.post("/auth/register", data={**NEW_USER, "username": "buyer"}).status_code == 200
    assert user_count(app) == before


def test_register_page_loads(client):
    assert client.get("/auth/register").status_code == 200


# ---------- email verification ----------

def test_verify_email_marks_verified_and_logs_in(app, client):
    client.post("/auth/register", data=NEW_USER)
    with app.app_context():
        token = generate_verify_token("new@example.com")
    assert client.get(f"/auth/verify-email/{token}").status_code == 302
    with app.app_context():
        assert User.query.filter_by(email="new@example.com").one().email_verified is True
    assert client.get("/account/").status_code == 200  # now logged in


def test_verify_email_with_bad_token_goes_to_resend_page(client):
    resp = client.get("/auth/verify-email/garbage")
    assert resp.status_code == 302
    assert "/auth/resend-verification" in resp.headers["Location"]


def test_verify_email_for_unknown_account(app, client):
    with app.app_context():
        token = generate_verify_token("ghost@example.com")
    resp = client.get(f"/auth/verify-email/{token}")
    assert resp.status_code == 302
    assert "/auth/register" in resp.headers["Location"]


def test_check_email_page(client):
    assert client.get("/auth/check-email").status_code == 302  # nothing pending
    client.post("/auth/register", data=NEW_USER)
    assert client.get("/auth/check-email").status_code == 200


def test_resend_verification(client, no_real_emails):
    assert client.get("/auth/resend-verification").status_code == 200
    client.post("/auth/resend-verification")  # nothing pending: no email
    assert len(no_real_emails["verify"]) == 0
    client.post("/auth/register", data=NEW_USER)
    client.post("/auth/resend-verification")
    assert len(no_real_emails["verify"]) == 2


# ---------- forgot / reset password ----------

def test_forgot_password_only_emails_verified_accounts(client, seeded, no_real_emails):
    assert client.get("/auth/forgot-password").status_code == 200
    client.post("/auth/forgot-password", data={"email": seeded["email"]})
    client.post("/auth/forgot-password", data={"email": "nobody@example.com"})
    assert len(no_real_emails["reset"]) == 1


def test_reset_password_flow(app, client, seeded):
    with app.app_context():
        token = generate_reset_token(seeded["email"])
    assert client.get(f"/auth/reset-password/{token}").status_code == 200

    resp = client.post(f"/auth/reset-password/{token}",
                       data={"password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD})
    assert resp.status_code == 302

    old = client.post("/auth/login", data={"email": seeded["email"], "password": seeded["password"]})
    assert old.status_code == 200  # old password rejected
    new = client.post("/auth/login", data={"email": seeded["email"], "password": NEW_PASSWORD})
    assert new.status_code == 302


@pytest.mark.parametrize("password, confirm", [(NEW_PASSWORD, "Different!Pass99"), ("weak", "weak")])
def test_reset_password_rejects_bad_passwords(app, client, seeded, password, confirm):
    with app.app_context():
        token = generate_reset_token(seeded["email"])
    resp = client.post(f"/auth/reset-password/{token}", data={"password": password, "confirm_password": confirm})
    assert resp.status_code == 200
    assert client.post("/auth/login", data={"email": seeded["email"], "password": seeded["password"]}).status_code == 302


def test_reset_password_with_bad_token(client):
    resp = client.get("/auth/reset-password/garbage")
    assert resp.status_code == 302
    assert "/auth/forgot-password" in resp.headers["Location"]


# ---------- login / logout ----------

def test_unknown_email_cannot_log_in(client):
    resp = client.post("/auth/login", data={"email": "nobody@example.com", "password": "whatever"})
    assert resp.status_code == 200


def test_logout_revokes_the_session(client, seeded, login):
    login(seeded["email"])
    assert client.get("/account/").status_code == 200
    assert client.get("/auth/logout").status_code == 302
    assert client.get("/account/").status_code == 302


def test_logged_in_user_is_redirected_away_from_login(client, seeded, login):
    login(seeded["email"])
    assert client.get("/auth/login").status_code == 302


@pytest.mark.parametrize("next_url, expected_end", [
    ("/shop", "/shop"),
    ("//evil.com", "/"),
    ("https://evil.com", "/"),
])
def test_login_next_redirect_is_safe(client, seeded, next_url, expected_end):
    resp = client.post(f"/auth/login?next={next_url}",
                       data={"email": seeded["email"], "password": seeded["password"]})
    assert resp.status_code == 302
    assert "evil" not in resp.headers["Location"]
    assert resp.headers["Location"].endswith(expected_end)


def test_remember_me_sets_a_remember_cookie(client, seeded):
    resp = client.post("/auth/login", data={
        "email": seeded["email"], "password": seeded["password"], "remember": "on",
    })
    assert any("remember_token" in c for c in resp.headers.getlist("Set-Cookie"))


# ---------- guest checkout ----------

def test_guest_page_loads(client):
    assert client.get("/auth/guest").status_code == 200


@pytest.mark.parametrize("data", [
    {"first_name": "Guest", "last_name": "", "phone": "01012345678"},
    {"first_name": "Guest", "last_name": "Buyer", "phone": "12"},
])
def test_guest_checkout_validates_input(app, client, data):
    assert client.post("/auth/guest", data=data).status_code == 200
    with app.app_context():
        assert User.query.filter(User.email.is_(None)).count() == 0


def test_guest_checkout_honours_next_url(client):
    resp = client.post("/auth/guest", data={
        "first_name": "Guest", "last_name": "Buyer", "phone": "01012345678", "next": "/cart/checkout",
    })
    assert resp.headers["Location"].endswith("/cart/checkout")


def test_logged_in_user_skips_guest_page(client, seeded, login):
    login(seeded["email"])
    assert client.get("/auth/guest").status_code == 302