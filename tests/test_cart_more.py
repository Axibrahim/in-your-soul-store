from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Address, DiscountCode, Order, ProductVariant, User

ADDRESS = {
    "street": "1 Test St", "building": "2", "floor": "3",
    "district": "Maadi", "governorate": "Cairo",
}


def checkout(client, **extra):
    return client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS, **extra})


def cart_count(client):
    return client.get("/cart/count").get_json()["count"]


def order_count(app):
    with app.app_context():
        return Order.query.count()


def make_code(app, **overrides):
    fields = dict(code="SAVE10", discount_type="percent", value=10)
    fields.update(overrides)
    with app.app_context():
        code = DiscountCode(**fields)
        db.session.add(code)
        db.session.commit()
        return code.id


def session_discount(client):
    with client.session_transaction() as sess:
        return sess.get("discount_code")


# ---------- cart page and quantities ----------

def test_cart_page_empty_and_with_items(client, seeded, add_to_cart):
    assert client.get("/cart/").status_code == 200
    add_to_cart(seeded["product_id"], quantity=2)
    resp = client.get("/cart/")
    assert resp.status_code == 200
    assert b"Test Tee" in resp.data
    assert cart_count(client) == 2


def test_update_cart_caps_at_stock_and_zero_removes(client, seeded, add_to_cart):
    add_to_cart(seeded["product_id"], quantity=1)
    key = f"{seeded['product_id']}_M"

    client.post("/cart/update", data={"key": key, "quantity": 3})
    assert cart_count(client) == 3
    client.post("/cart/update", data={"key": key, "quantity": 99})
    assert cart_count(client) == 5  # stock is 5
    client.post("/cart/update", data={"key": key, "quantity": 0})
    assert cart_count(client) == 0


def test_remove_from_cart(client, seeded, add_to_cart):
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/remove", data={"key": f"{seeded['product_id']}_M"})
    assert cart_count(client) == 0


def test_adding_the_same_item_accumulates_but_respects_stock(client, seeded, add_to_cart):
    add_to_cart(seeded["product_id"], quantity=2)
    assert add_to_cart(seeded["product_id"], quantity=2).status_code == 200
    assert cart_count(client) == 4
    assert add_to_cart(seeded["product_id"], quantity=2).status_code == 400  # 6 > 5 in stock


@pytest.mark.parametrize("quantity", [0, 51])
def test_add_rejects_invalid_quantity(client, seeded, add_to_cart, quantity):
    assert add_to_cart(seeded["product_id"], quantity=quantity).status_code == 400


def test_add_rejects_missing_size_and_unknown_product(client, seeded, add_to_cart):
    assert client.post("/cart/add", data={"product_id": seeded["product_id"], "quantity": 1}).status_code == 400
    assert add_to_cart(999999).status_code == 404


# ---------- discount codes ----------

def test_apply_and_remove_discount(app, client, seeded, add_to_cart):
    make_code(app)
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/apply-discount", data={"code": "save10"})
    assert session_discount(client) == "SAVE10"
    client.post("/cart/remove-discount", data={})
    assert session_discount(client) is None


@pytest.mark.parametrize("code_kwargs, typed", [
    ({}, "NOPE"),                                              # unknown code
    ({}, ""),                                                  # empty
    ({"is_active": False}, "SAVE10"),                          # disabled
    ({"min_subtotal": 2000}, "SAVE10"),                        # cart too small
    ({"max_uses": 1, "uses_count": 1}, "SAVE10"),              # used up
    ({"expires_at": datetime.utcnow() - timedelta(days=1)}, "SAVE10"),  # expired
])
def test_invalid_discount_codes_are_not_applied(app, client, seeded, add_to_cart, code_kwargs, typed):
    make_code(app, **code_kwargs)
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/apply-discount", data={"code": typed})
    assert session_discount(client) is None


def test_apply_discount_can_return_to_checkout_page(app, client, seeded, add_to_cart):
    make_code(app)
    add_to_cart(seeded["product_id"], quantity=2)
    resp = client.post("/cart/apply-discount", data={"code": "SAVE10", "next": "checkout"})
    assert resp.headers["Location"].endswith("/cart/checkout")


def test_discount_that_expires_before_checkout_blocks_the_order(app, client, seeded, login, add_to_cart):
    code_id = make_code(app)
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/apply-discount", data={"code": "SAVE10"})
    with app.app_context():
        db.session.get(DiscountCode, code_id).expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

    assert checkout(client).status_code == 302
    assert order_count(app) == 0
    assert session_discount(client) is None


def test_stale_discount_is_cleared_when_viewing_the_cart(app, client, seeded, add_to_cart):
    code_id = make_code(app)
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/apply-discount", data={"code": "SAVE10"})
    with app.app_context():
        db.session.get(DiscountCode, code_id).is_active = False
        db.session.commit()
    assert client.get("/cart/").status_code == 200
    assert session_discount(client) is None


# ---------- checkout ----------

def test_checkout_page_needs_items_in_cart(client, seeded, login, add_to_cart):
    login(seeded["email"])
    resp = client.get("/cart/checkout")
    assert resp.status_code == 302  # empty cart goes back to the cart page
    add_to_cart(seeded["product_id"])
    assert client.get("/cart/checkout").status_code == 200


def test_checkout_rejects_unknown_payment_method(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    checkout(client, payment_method="bitcoin")
    assert order_count(app) == 0


def test_checkout_rejects_incomplete_address(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    checkout(client, street="")
    assert order_count(app) == 0


def test_online_payment_gets_a_two_hour_deadline(app, client, seeded, login, add_to_cart, get_stock):
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=2)
    checkout(client, payment_method="vodafone_cash")
    with app.app_context():
        order = Order.query.one()
        remaining = order.payment_deadline - datetime.utcnow()
        assert timedelta(hours=1, minutes=55) < remaining <= timedelta(hours=2)
    assert get_stock(seeded["product_id"]) == 3


def test_free_shipping_from_1500(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=3)  # 3 x 500 = 1500
    checkout(client)
    with app.app_context():
        order = Order.query.one()
        assert order.shipping_cost == 0
        assert order.total == 1500


def test_checkout_redirects_to_the_new_order(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    resp = checkout(client)
    with app.app_context():
        order_id = Order.query.one().id
    assert resp.headers["Location"].endswith(f"/account/order/{order_id}")
    assert cart_count(client) == 0  # cart emptied


def test_manual_address_is_saved_to_the_address_book(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    checkout(client)
    with app.app_context():
        address = Address.query.one()
        assert address.user_id == seeded["user_id"]
        assert address.is_default is True


def test_checkout_with_a_saved_address(app, client, seeded, login, add_to_cart):
    with app.app_context():
        address = Address(user_id=seeded["user_id"], label="Work", street="9 Saved St", building="1",
                          floor="1", district="Dokki", governorate="Giza")
        db.session.add(address)
        db.session.commit()
        address_id = address.id
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    client.post("/cart/checkout", data={"payment_method": "cod", "address_id": address_id})
    with app.app_context():
        assert Order.query.one().get_shipping_address()["street"] == "9 Saved St"
        assert Address.query.count() == 1  # nothing extra saved


def test_checkout_rejects_someone_elses_saved_address(app, client, seeded, other_user, login, add_to_cart):
    with app.app_context():
        address = Address(user_id=other_user["id"], label="Home", street="x", building="1",
                          floor="1", district="d", governorate="g")
        db.session.add(address)
        db.session.commit()
        address_id = address.id
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    client.post("/cart/checkout", data={"payment_method": "cod", "address_id": address_id})
    assert order_count(app) == 0


def test_guest_can_check_out(app, client, add_to_cart, seeded):
    client.post("/auth/guest", data={"first_name": "Gus", "last_name": "Guest", "phone": "01011112222"})
    add_to_cart(seeded["product_id"])
    assert checkout(client).status_code == 302
    with app.app_context():
        order = Order.query.one()
        assert db.session.get(User, order.user_id).email is None


def test_variant_removed_after_adding_blocks_the_order(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    with app.app_context():
        ProductVariant.query.filter_by(product_id=seeded["product_id"], size="M").delete()
        db.session.commit()
    checkout(client)
    assert order_count(app) == 0


def test_database_failure_at_checkout_rolls_back_cleanly(app, client, seeded, login, add_to_cart, get_stock, monkeypatch):
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=2)

    def boom():
        raise RuntimeError("database went away")

    monkeypatch.setattr(db.session, "commit", boom)
    resp = checkout(client)
    monkeypatch.undo()

    assert resp.status_code == 302
    assert "/cart/checkout" in resp.headers["Location"]
    assert order_count(app) == 0
    assert get_stock(seeded["product_id"]) == 5  # stock put back by the rollback