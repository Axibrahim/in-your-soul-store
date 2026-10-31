from datetime import datetime, timedelta

from flask_login import login_user

from app import auth_guard, db
from app.models import User


def set_user_field(app, user_id, **fields):
    with app.app_context():
        User.query.filter_by(id=user_id).update(fields)
        db.session.commit()


def get_issued_at(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id).session_issued_at


def sent_to_login(resp):
    return resp.status_code == 302 and "/auth/login" in resp.headers["Location"]


# ---------- per-request session checks ----------

def test_a_new_login_signs_out_the_old_session(app, client, seeded, login):
    login(seeded["email"])
    assert client.get("/account/").status_code == 200

    other_browser = app.test_client()
    resp = other_browser.post("/auth/login", data={"email": seeded["email"], "password": seeded["password"]})
    assert resp.status_code == 302
    assert other_browser.get("/account/").status_code == 200

    assert sent_to_login(client.get("/account/"))


def test_session_older_than_seven_days_is_rejected(app, client, seeded, login):
    login(seeded["email"])
    set_user_field(app, seeded["user_id"], session_issued_at=datetime.utcnow() - timedelta(days=8))
    assert sent_to_login(client.get("/account/"))


def test_revoked_token_is_rejected(app, client, seeded, login):
    login(seeded["email"])
    set_user_field(app, seeded["user_id"], session_token=None)
    assert sent_to_login(client.get("/account/"))


def test_missing_cookie_token_is_rejected(client, seeded, login):
    login(seeded["email"])
    with client.session_transaction() as sess:
        sess.pop("_auth_token")
    assert sent_to_login(client.get("/account/"))


def test_last_seen_stamp_refreshes_only_when_over_an_hour_old(app, client, seeded, login):
    login(seeded["email"])

    set_user_field(app, seeded["user_id"], session_issued_at=datetime.utcnow() - timedelta(hours=2))
    assert client.get("/account/").status_code == 200
    assert get_issued_at(app, seeded["user_id"]) > datetime.utcnow() - timedelta(minutes=5)

    recent = datetime.utcnow() - timedelta(minutes=10)
    set_user_field(app, seeded["user_id"], session_issued_at=recent)
    assert client.get("/account/").status_code == 200
    assert get_issued_at(app, seeded["user_id"]) == recent  # no needless database write


# ---------- decorators ----------

def _login_in_request(app, user_id):
    user = db.session.get(User, user_id)
    login_user(user)
    return user


def test_token_required_passes_valid_sessions(app, seeded, monkeypatch):
    with app.test_request_context():
        _login_in_request(app, seeded["user_id"])
        monkeypatch.setattr(auth_guard, "validate_session_token", lambda: True)
        assert auth_guard.token_required(lambda: "ok")() == "ok"


def test_token_required_logs_out_invalid_sessions(app, seeded, monkeypatch):
    with app.test_request_context():
        _login_in_request(app, seeded["user_id"])
        monkeypatch.setattr(auth_guard, "validate_session_token", lambda: False)
        resp = auth_guard.token_required(lambda: "ok")()
        assert sent_to_login(resp)


def test_token_required_admin_rules(app, seeded, monkeypatch):
    monkeypatch.setattr(auth_guard, "validate_session_token", lambda: True)

    with app.test_request_context():  # not logged in
        assert sent_to_login(auth_guard.token_required_admin(lambda: "ok")())

    with app.test_request_context():  # logged in, not an admin
        _login_in_request(app, seeded["user_id"])
        resp = auth_guard.token_required_admin(lambda: "ok")()
        assert resp.status_code == 302 and "/auth/login" not in resp.headers["Location"]

    set_user_field(app, seeded["user_id"], is_admin=True)
    with app.test_request_context():  # admin
        _login_in_request(app, seeded["user_id"])
        assert auth_guard.token_required_admin(lambda: "ok")() == "ok"

    monkeypatch.setattr(auth_guard, "validate_session_token", lambda: False)
    with app.test_request_context():  # admin with an invalid session
        _login_in_request(app, seeded["user_id"])
        assert sent_to_login(auth_guard.token_required_admin(lambda: "ok")())