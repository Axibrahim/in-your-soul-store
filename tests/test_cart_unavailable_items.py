from app import db
from app.models import Order, Product, ProductVariant

ADDRESS = {
    "street": "1 Test St", "building": "2", "floor": "3",
    "district": "Maadi", "governorate": "Cairo",
}


def checkout(client):
    return client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS})


def cart_count(client):
    return client.get("/cart/count").get_json()["count"]


def test_deactivated_product_cannot_be_added(app, client, seeded, add_to_cart):
    with app.app_context():
        db.session.get(Product, seeded["product_id"]).is_active = False
        db.session.commit()
    assert add_to_cart(seeded["product_id"]).status_code == 404


def test_checkout_is_blocked_and_cart_cleaned_when_product_is_deactivated(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    with app.app_context():
        db.session.get(Product, seeded["product_id"]).is_active = False
        db.session.commit()

    resp = checkout(client)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/cart/")
    with app.app_context():
        assert Order.query.count() == 0
    assert cart_count(client) == 0


def test_checkout_is_blocked_when_product_was_deleted(app, client, seeded, login, add_to_cart):
    login(seeded["email"])
    add_to_cart(seeded["product_id"])
    with app.app_context():
        ProductVariant.query.filter_by(product_id=seeded["product_id"]).delete()
        Product.query.filter_by(id=seeded["product_id"]).delete()
        db.session.commit()

    assert checkout(client).status_code == 302
    with app.app_context():
        assert Order.query.count() == 0  # no empty order with just a shipping fee
    assert cart_count(client) == 0