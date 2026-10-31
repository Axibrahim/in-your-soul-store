import io
from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Address, RefundImage, RefundRequest, User

NEW_PASSWORD = "N3w!Strong#Pass99"
ADDRESS_FORM = {
    "label": "Home", "street": "1 Test St", "building": "2", "floor": "3",
    "district": "Maadi", "governorate": "Cairo",
}


@pytest.fixture(autouse=True)
def no_real_emails(monkeypatch):
    sent = {"verify": [], "refund": []}
    monkeypatch.setattr("app.routes.account.send_verification_email",
                        lambda *a, **k: sent["verify"].append(a) or True)
    monkeypatch.setattr("app.routes.account.send_refund_request_email",
                        lambda *a, **k: sent["refund"].append(a) or True)
    return sent


@pytest.fixture()
def fake_uploads(monkeypatch):
    """Replace the Supabase image upload with a fake that returns a URL."""
    monkeypatch.setattr("app.routes.admin.save_product_image",
                        lambda file, folder=None: f"https://img.example/{folder}/{file.filename}")


def password_ok(app, user_id, password):
    with app.app_context():
        return db.session.get(User, user_id).check_password(password)


# ---------- pages ----------

@pytest.mark.parametrize("path", ["/account/", "/account/orders", "/account/profile", "/account/addresses"])
def test_account_pages_load_for_logged_in_user(client, seeded, login, path):
    login(seeded["email"])
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", ["/account/", "/account/orders", "/account/profile", "/account/addresses"])
def test_account_pages_require_login(client, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_order_detail_shows_own_order_but_not_someone_elses(client, seeded, other_user, order_factory, login):
    mine = order_factory()
    theirs = order_factory(user_id=other_user["id"])
    login(seeded["email"])
    assert client.get(f"/account/order/{mine}").status_code == 200
    assert client.get(f"/account/order/{theirs}").status_code == 404


def test_track_order_redirects_to_order_page(app, client, seeded, other_user, order_factory, login):
    mine = order_factory()
    theirs = order_factory(user_id=other_user["id"])
    with app.app_context():
        from app.models import Order
        mine_number = db.session.get(Order, mine).order_number
        theirs_number = db.session.get(Order, theirs).order_number
    login(seeded["email"])

    resp = client.get(f"/account/track-order/{mine_number}")
    assert resp.status_code == 302
    assert f"/account/order/{mine}" in resp.headers["Location"]
    assert client.get(f"/account/track-order/{theirs_number}").status_code == 404
    assert client.get("/account/track-order/FRK-NOPE").status_code == 404


# ---------- profile ----------

def test_profile_update(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/profile", data={"first_name": "Neo", "last_name": "Anderson", "phone": "01099999999"})
    with app.app_context():
        user = db.session.get(User, seeded["user_id"])
        assert (user.first_name, user.last_name, user.phone) == ("Neo", "Anderson", "01099999999")


def test_profile_update_rejects_empty_name(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/profile", data={"first_name": "", "last_name": "Anderson", "phone": "0100"})
    with app.app_context():
        assert db.session.get(User, seeded["user_id"]).first_name == "Test"


# ---------- change password ----------

@pytest.mark.parametrize("current, new, confirm", [
    ("wrong-current", NEW_PASSWORD, NEW_PASSWORD),
    (None, NEW_PASSWORD, "Different!Pass99"),
    (None, "weak", "weak"),
])
def test_change_password_rejections_keep_old_password(app, client, seeded, login, current, new, confirm):
    login(seeded["email"])
    client.post("/account/change-password", data={
        "current_password": current or seeded["password"],
        "new_password": new, "confirm_password": confirm,
    })
    assert password_ok(app, seeded["user_id"], seeded["password"])


def test_change_password_success(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/change-password", data={
        "current_password": seeded["password"],
        "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
    })
    assert password_ok(app, seeded["user_id"], NEW_PASSWORD)


# ---------- addresses ----------

def test_add_address_and_default_switching(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/addresses/add", data={**ADDRESS_FORM, "is_default": "on"})
    client.post("/account/addresses/add", data={**ADDRESS_FORM, "label": "Work", "is_default": "on"})
    with app.app_context():
        addresses = Address.query.filter_by(user_id=seeded["user_id"]).order_by(Address.id).all()
        assert [a.is_default for a in addresses] == [False, True]


def test_add_address_requires_all_main_fields(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/addresses/add", data={**ADDRESS_FORM, "street": ""})
    with app.app_context():
        assert Address.query.count() == 0


def test_set_default_and_delete_address(app, client, seeded, login):
    login(seeded["email"])
    client.post("/account/addresses/add", data=ADDRESS_FORM)
    client.post("/account/addresses/add", data={**ADDRESS_FORM, "label": "Work"})
    with app.app_context():
        first, second = [a.id for a in Address.query.order_by(Address.id).all()]

    resp = client.post(f"/account/addresses/{second}/set-default")
    assert resp.get_json() == {"success": True}
    with app.app_context():
        assert db.session.get(Address, second).is_default is True
        assert db.session.get(Address, first).is_default is False

    client.post(f"/account/addresses/{first}/delete")
    with app.app_context():
        assert db.session.get(Address, first) is None


def test_cannot_touch_someone_elses_address(app, client, seeded, other_user, login):
    with app.app_context():
        address = Address(user_id=other_user["id"], label="Home", street="x", building="1",
                          floor="1", district="d", governorate="g")
        db.session.add(address)
        db.session.commit()
        address_id = address.id
    login(seeded["email"])
    assert client.post(f"/account/addresses/{address_id}/delete").status_code == 404
    assert client.post(f"/account/addresses/{address_id}/set-default").status_code == 404


# ---------- complete registration (guest -> full account) ----------

def become_guest(client):
    resp = client.post("/auth/guest", data={"first_name": "Gus", "last_name": "Guest", "phone": "01011112222"})
    assert resp.status_code == 302


COMPLETE = {
    "username": "guestdone", "email": "guest@example.com",
    "password": "Gu3st!Secure#Pw1", "confirm_password": "Gu3st!Secure#Pw1",
}


def test_full_account_is_sent_away_from_complete_registration(client, seeded, login):
    login(seeded["email"])
    resp = client.get("/account/complete-registration")
    assert resp.status_code == 302
    assert "/account/profile" in resp.headers["Location"]


def test_guest_can_complete_registration(app, client, no_real_emails):
    become_guest(client)
    assert client.get("/account/complete-registration").status_code == 200
    resp = client.post("/account/complete-registration", data=COMPLETE)
    assert resp.status_code == 302
    with app.app_context():
        user = User.query.filter_by(username="guestdone").one()
        assert user.email == "guest@example.com"
        assert user.email_verified is False
    assert len(no_real_emails["verify"]) == 1


@pytest.mark.parametrize("override", [
    {"confirm_password": "Different!Pass99"},
    {"password": "weak", "confirm_password": "weak"},
    {"email": "not-an-email"},
    {"username": ""},
    {"email": "buyer@example.com"},   # already registered
    {"username": "buyer"},            # already taken
])
def test_complete_registration_rejects_bad_input(app, client, seeded, override):
    become_guest(client)
    client.post("/account/complete-registration", data={**COMPLETE, **override})
    with app.app_context():
        assert User.query.filter(User.email.is_(None)).count() == 1  # still a guest


# ---------- refunds ----------

def post_refund(client, order_id, reason="Too small", item_photo=True, receipt_photo=False):
    data = {"reason": reason}
    if item_photo:
        data["item_photo"] = (io.BytesIO(b"fake-image"), "item.jpg")
    if receipt_photo:
        data["receipt_photo"] = (io.BytesIO(b"fake-image"), "receipt.jpg")
    return client.post(f"/account/order/{order_id}/refund", data=data, content_type="multipart/form-data")


def refund_counts(app):
    with app.app_context():
        return RefundRequest.query.count(), RefundImage.query.count()


def delivered_recently():
    return datetime.utcnow() - timedelta(hours=1)


def test_delivered_order_page_loads(client, seeded, order_factory, login):
    order_id = order_factory(status="delivered", delivered_at=delivered_recently())
    login(seeded["email"])
    assert client.get(f"/account/order/{order_id}").status_code == 200


def test_refund_request_with_both_photos(app, client, seeded, order_factory, login, fake_uploads, no_real_emails):
    order_id = order_factory(status="delivered", delivered_at=delivered_recently())
    login(seeded["email"])
    assert post_refund(client, order_id, receipt_photo=True).status_code == 302
    assert refund_counts(app) == (1, 2)
    assert len(no_real_emails["refund"]) == 1


def test_refund_still_saved_if_a_photo_upload_fails(app, client, seeded, order_factory, login, monkeypatch):
    monkeypatch.setattr("app.routes.admin.save_product_image", lambda file, folder=None: None)
    order_id = order_factory(status="delivered", delivered_at=delivered_recently())
    login(seeded["email"])
    post_refund(client, order_id)
    assert refund_counts(app) == (1, 0)


@pytest.mark.parametrize("order_kwargs, post_kwargs", [
    ({"status": "pending"}, {}),                                                            # not delivered
    ({"status": "delivered", "delivered_at": datetime.utcnow() - timedelta(days=3)}, {}),   # window closed
    ({"status": "delivered", "delivered_at": datetime.utcnow()}, {"reason": ""}),           # no reason
    ({"status": "delivered", "delivered_at": datetime.utcnow()}, {"item_photo": False}),    # no photo
])
def test_refund_is_rejected(app, client, seeded, order_factory, login, fake_uploads, order_kwargs, post_kwargs):
    order_id = order_factory(**order_kwargs)
    login(seeded["email"])
    post_refund(client, order_id, **post_kwargs)
    assert refund_counts(app) == (0, 0)


def test_duplicate_and_daily_limit_on_refunds(app, client, seeded, order_factory, login, fake_uploads):
    first = order_factory(status="delivered", delivered_at=delivered_recently())
    second = order_factory(status="delivered", delivered_at=delivered_recently())
    login(seeded["email"])

    post_refund(client, first)
    post_refund(client, first)   # same order again: blocked
    post_refund(client, second)  # different order, same day: blocked by the daily limit
    assert refund_counts(app)[0] == 1