from app import db
from app.models import User


def test_login_succeeds_for_verified_user(client, seeded, login):
    resp = login(seeded["email"])
    assert resp.status_code == 302


def test_wrong_password_stays_on_login(client, seeded, login):
    resp = login(seeded["email"], password="not-the-password")
    assert resp.status_code == 200


def test_unverified_user_is_sent_to_check_email(app, client, login):
    with app.app_context():
        user = User(username="newbie", email="newbie@example.com", first_name="N",
                    last_name="B", phone="01000000001", email_verified=False)
        user.set_password("Passw0rd!x1")
        db.session.add(user)
        db.session.commit()
    resp = login("newbie@example.com")
    assert resp.status_code == 302
    assert "/auth/check-email" in resp.headers["Location"]


def test_guest_checkout_creates_guest_user(app, client):
    resp = client.post("/auth/guest", data={
        "first_name": "Guest", "last_name": "Buyer", "phone": "01012345678", "next": "",
    })
    assert resp.status_code == 302
    with app.app_context():
        assert User.query.filter(User.email.is_(None)).count() == 1


def test_admin_area_redirects_anonymous_to_login(client):
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_admin_area_blocks_normal_user(client, seeded, login):
    login(seeded["email"])
    resp = client.get("/admin/")
    assert resp.status_code == 302
    assert "/admin" not in resp.headers["Location"]