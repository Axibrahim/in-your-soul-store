from datetime import datetime, timedelta

from app import db
from app.models import DiscountCode, Order, OrderItem, ProductVariant
from app.routes.main import cancel_expired_orders

ADDRESS = {
    "street": "1 Test St", "building": "2", "floor": "3",
    "district": "Maadi", "governorate": "Cairo",
}


def test_add_to_cart_counts_items(client, seeded, add_to_cart):
    resp = add_to_cart(seeded["product_id"], quantity=2)
    assert resp.status_code == 200
    assert resp.get_json()["cart_count"] == 2


def test_cannot_add_more_than_stock(client, seeded, add_to_cart):
    assert add_to_cart(seeded["product_id"], quantity=6).status_code == 400


def test_cannot_add_unknown_size(client, seeded, add_to_cart):
    assert add_to_cart(seeded["product_id"], size="XXL").status_code == 400


def test_checkout_requires_login(client, seeded, add_to_cart):
    add_to_cart(seeded["product_id"])
    resp = client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS})
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_cod_checkout_creates_order_and_reduces_stock(app, client, seeded, login, add_to_cart, get_stock):
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=2)
    resp = client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS})
    assert resp.status_code == 302

    with app.app_context():
        order = Order.query.one()
        assert order.order_number.startswith("FRK-")
        assert order.status == "pending"
        assert order.subtotal == 1000.0
        assert order.shipping_cost == 80
        assert order.total == 1080.0
    assert get_stock(seeded["product_id"]) == 3


def test_checkout_rejects_item_that_just_sold_out(app, client, seeded, login, add_to_cart, get_stock):
    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=3)
    # Someone else buys most of the stock after this customer filled the cart.
    with app.app_context():
        ProductVariant.query.filter_by(product_id=seeded["product_id"], size="M").update({"stock": 1})
        db.session.commit()

    resp = client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS})
    assert resp.status_code == 302
    with app.app_context():
        assert Order.query.count() == 0
    assert get_stock(seeded["product_id"]) == 1


def test_discount_code_is_applied_and_counted(app, client, seeded, login, add_to_cart):
    with app.app_context():
        db.session.add(DiscountCode(code="SAVE10", discount_type="percent", value=10))
        db.session.commit()

    login(seeded["email"])
    add_to_cart(seeded["product_id"], quantity=2)
    client.post("/cart/apply-discount", data={"code": "save10"})
    client.post("/cart/checkout", data={"payment_method": "cod", **ADDRESS})

    with app.app_context():
        order = Order.query.one()
        assert order.discount_code == "SAVE10"
        assert order.discount_amount == 100.0
        assert order.total == 980.0
        assert DiscountCode.query.filter_by(code="SAVE10").one().uses_count == 1


def test_cancel_expired_orders_restocks_exactly_once(app, seeded, get_stock):
    pid = seeded["product_id"]
    with app.app_context():
        variant = ProductVariant.query.filter_by(product_id=pid, size="M").first()
        order = Order(
            order_number="FRK-00000001",
            user_id=seeded["user_id"],
            payment_method="instapay",
            payment_status="unpaid",
            status="pending",
            payment_deadline=datetime.utcnow() - timedelta(hours=1),
            total=1000,
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(
            order_id=order.id, product_id=pid, variant_id=variant.id,
            product_name="Test Tee", size="M", quantity=2,
            unit_price=500, total_price=1000,
        ))
        db.session.commit()
        order_id = order.id

    with app.app_context():
        cancel_expired_orders()
    assert get_stock(pid) == 7  # 5 + 2 returned

    with app.app_context():
        assert db.session.get(Order, order_id).status == "cancelled"
        cancel_expired_orders()  # running it again must not restock again
    assert get_stock(pid) == 7