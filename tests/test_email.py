import threading
from types import SimpleNamespace

import pytest
import resend

from app import db
from app.email import (
    confirm_reset_token, confirm_verify_token, generate_reset_token, generate_verify_token,
    send_admin_new_order_email, send_order_status_email, send_refund_request_email,
    send_refund_status_email, send_reset_email, send_verification_email,
)
from app.models import Order

ALL_ENV = ("RESEND_API_KEY", "RESEND_FROM_EMAIL", "RESEND_ORDERS_FROM_EMAIL", "ADMIN_NOTIFY_EMAIL")
ORDER = SimpleNamespace(id=1, order_number="FRK-00000009")


@pytest.fixture()
def resend_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "hello@example.com")
    monkeypatch.setenv("RESEND_ORDERS_FROM_EMAIL", "orders@example.com")
    monkeypatch.setenv("ADMIN_NOTIFY_EMAIL", "owner@example.com")
    monkeypatch.setenv("BASE_URL", "https://shop.example.com")


@pytest.fixture()
def no_resend_env(monkeypatch):
    for name in ALL_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def sent(monkeypatch):
    """Captures what would have been sent to Resend."""
    calls = []
    monkeypatch.setattr(resend.Emails, "send", staticmethod(lambda payload: calls.append(payload) or {"id": "x"}))
    return calls


# ---------- tokens ----------

def test_verify_token_round_trip(app):
    with app.app_context():
        token = generate_verify_token("a@example.com")
        assert confirm_verify_token(token) == "a@example.com"


def test_reset_token_round_trip(app):
    with app.app_context():
        token = generate_reset_token("a@example.com")
        assert confirm_reset_token(token) == "a@example.com"


def test_tokens_reject_garbage_and_wrong_purpose(app):
    with app.app_context():
        assert confirm_verify_token("not-a-token") is None
        assert confirm_reset_token("not-a-token") is None
        assert confirm_verify_token(generate_reset_token("a@example.com")) is None
        assert confirm_reset_token(generate_verify_token("a@example.com")) is None


def test_expired_tokens_are_rejected(app):
    app.config["EMAIL_VERIFY_MAX_AGE_SECONDS"] = -1
    app.config["PASSWORD_RESET_MAX_AGE_SECONDS"] = -1
    with app.app_context():
        assert confirm_verify_token(generate_verify_token("a@example.com")) is None
        assert confirm_reset_token(generate_reset_token("a@example.com")) is None


# ---------- not configured ----------

def test_senders_return_false_when_resend_is_not_configured(app, no_resend_env):
    refund = SimpleNamespace(status="approved")
    with app.test_request_context():
        assert send_verification_email("c@example.com", "tok") is False
        assert send_reset_email("c@example.com", "tok") is False
        assert send_order_status_email("c@example.com", "FRK-1", "shipped") is False
        assert send_refund_request_email("c@example.com", ORDER, refund) is False
        assert send_refund_status_email("c@example.com", ORDER, refund) is False
    with app.app_context():
        assert send_admin_new_order_email(None) is False


# ---------- payloads ----------

def test_verification_email_payload(app, resend_env, sent):
    with app.test_request_context():
        assert send_verification_email("c@example.com", "tok", first_name="Sam") is True
    payload = sent[0]
    assert payload["to"] == ["c@example.com"]
    assert payload["from"] == "hello@example.com"
    variables = payload["template"]["variables"]
    assert variables["first_name"] == "Sam"
    assert variables["verification_url"] == "https://shop.example.com/auth/verify-email/tok"


def test_verification_email_defaults_name_to_friend(app, resend_env, sent):
    with app.test_request_context():
        send_verification_email("c@example.com", "tok")
    assert sent[0]["template"]["variables"]["first_name"] == "Friend"


def test_reset_email_payload(app, resend_env, sent):
    with app.test_request_context():
        assert send_reset_email("c@example.com", "tok") is True
    payload = sent[0]
    assert payload["subject"] == "Reset your IN YOUR SOUL password"
    assert "https://shop.example.com/auth/reset-password/tok" in payload["text"]


def test_order_status_email_payload(app, resend_env, sent):
    with app.test_request_context():
        assert send_order_status_email("c@example.com", "FRK-1", "shipped", first_name="Sam") is True
    payload = sent[0]
    assert payload["from"] == "orders@example.com"
    assert payload["subject"] == "Update on your order #FRK-1"
    variables = payload["template"]["variables"]
    assert variables["order_status"] == "shipped"
    assert variables["order_tracking_url"] == "https://shop.example.com/account/track-order/FRK-1"


def test_refund_request_email_payload(app, resend_env, sent):
    with app.test_request_context():
        assert send_refund_request_email("c@example.com", ORDER, SimpleNamespace(status="pending"),
                                         first_name="Sam") is True
    assert "FRK-00000009" in sent[0]["subject"]
    assert "Hi Sam" in sent[0]["text"]


@pytest.mark.parametrize("status, expected_text", [("approved", "has been approved"), ("rejected", "was not approved")])
def test_refund_status_email_wording(app, resend_env, sent, status, expected_text):
    with app.test_request_context():
        assert send_refund_status_email("c@example.com", ORDER, SimpleNamespace(status=status)) is True
    assert expected_text in sent[0]["text"]


def test_send_failures_return_false_instead_of_raising(app, resend_env, monkeypatch):
    def boom(payload):
        raise RuntimeError("Resend is down")

    monkeypatch.setattr(resend.Emails, "send", staticmethod(boom))
    refund = SimpleNamespace(status="approved")
    with app.test_request_context():
        assert send_verification_email("c@example.com", "tok") is False
        assert send_reset_email("c@example.com", "tok") is False
        assert send_order_status_email("c@example.com", "FRK-1") is False
        assert send_refund_request_email("c@example.com", ORDER, refund) is False
        assert send_refund_status_email("c@example.com", ORDER, refund) is False


# ---------- admin new-order notification ----------

def test_admin_new_order_email_is_sent_in_the_background(app, seeded, order_factory, resend_env, monkeypatch):
    done = threading.Event()
    calls = []

    def fake_send(payload):
        calls.append(payload)
        done.set()
        return {}

    monkeypatch.setattr(resend.Emails, "send", staticmethod(fake_send))
    order_id = order_factory(qty=2)
    with app.app_context():
        order = db.session.get(Order, order_id)
        assert send_admin_new_order_email(order) is True

    assert done.wait(timeout=5)
    payload = calls[0]
    assert payload["to"] == ["owner@example.com"]
    assert "FRK-" in payload["subject"]
    assert "Test Tee (M) x2" in payload["text"]


def test_admin_new_order_email_never_raises_on_bad_order(app, resend_env):
    with app.app_context():
        assert send_admin_new_order_email(object()) is False