import pytest

from app import db
from app.models import (
    Category, DiscountCode, Order, OrderItem, Product, ProductVariant, RefundRequest, User,
)

PASSWORD = "Passw0rd!x1"


@pytest.fixture(autouse=True)
def no_real_emails(monkeypatch):
    """Admin status changes send emails; never hit Resend from tests."""
    monkeypatch.setattr("app.routes.admin.send_order_status_email", lambda *a, **k: None)
    monkeypatch.setattr("app.email.send_refund_status_email", lambda *a, **k: None)


@pytest.fixture()
def admin(app, seeded, login):
    """Create an admin user and log in as them."""
    with app.app_context():
        user = User(
            username="boss", email="admin@example.com", first_name="Admin",
            last_name="Boss", phone="01000000009", email_verified=True, is_admin=True,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        admin_id = user.id
    assert login("admin@example.com").status_code == 302
    return {"id": admin_id, "email": "admin@example.com"}


def make_order(app, seeded, status="pending", qty=2, number="FRK-00000002"):
    """An order with one item (size M). Stock is NOT deducted here."""
    with app.app_context():
        pid = seeded["product_id"]
        variant = ProductVariant.query.filter_by(product_id=pid, size="M").first()
        order = Order(
            order_number=number, user_id=seeded["user_id"], payment_method="cod",
            status=status, total=500 * qty,
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(
            order_id=order.id, product_id=pid, variant_id=variant.id,
            product_name="Test Tee", size="M", quantity=qty,
            unit_price=500, total_price=500 * qty,
        ))
        db.session.commit()
        return order.id


# ---------- access control ----------

@pytest.mark.parametrize("path", [
    "/admin/", "/admin/products", "/admin/products/add", "/admin/orders",
    "/admin/categories", "/admin/users", "/admin/discounts", "/admin/refunds",
])
def test_admin_pages_load(client, admin, path):
    assert client.get(path).status_code == 200


def test_admin_detail_pages_load(app, client, admin, seeded):
    order_id = make_order(app, seeded)
    assert client.get(f"/admin/orders/{order_id}").status_code == 200
    assert client.get(f"/admin/products/{seeded['product_id']}/edit").status_code == 200


def test_normal_user_cannot_use_admin_actions(app, client, seeded, login):
    login(seeded["email"])
    resp = client.post("/admin/categories/add", data={"name": "Sneaky"})
    assert resp.status_code == 302
    resp = client.post(f"/admin/products/{seeded['product_id']}/toggle")
    assert resp.status_code == 302
    with app.app_context():
        assert Category.query.filter_by(name="Sneaky").count() == 0
        assert db.session.get(Product, seeded["product_id"]).is_active is True


# ---------- categories ----------

def test_add_category_and_reject_duplicate(app, client, admin):
    client.post("/admin/categories/add", data={"name": "T-Shirts"})
    client.post("/admin/categories/add", data={"name": "T-Shirts"})
    with app.app_context():
        cats = Category.query.filter_by(slug="t-shirts").all()
        assert len(cats) == 1


# ---------- discounts ----------

def test_add_discount_code(app, client, admin):
    client.post("/admin/discounts/add", data={
        "code": "vip20", "discount_type": "percent", "value": "20",
    })
    with app.app_context():
        code = DiscountCode.query.filter_by(code="VIP20").one()
        assert code.value == 20


def test_rejects_percent_discount_over_100(app, client, admin):
    client.post("/admin/discounts/add", data={
        "code": "BAD", "discount_type": "percent", "value": "150",
    })
    with app.app_context():
        assert DiscountCode.query.filter_by(code="BAD").count() == 0


def test_toggle_and_delete_discount(app, client, admin):
    with app.app_context():
        dc = DiscountCode(code="SAVE5", discount_type="fixed", value=5)
        db.session.add(dc)
        db.session.commit()
        dc_id = dc.id

    client.post(f"/admin/discounts/{dc_id}/toggle")
    with app.app_context():
        assert db.session.get(DiscountCode, dc_id).is_active is False

    client.post(f"/admin/discounts/{dc_id}/delete")
    with app.app_context():
        assert db.session.get(DiscountCode, dc_id) is None


# ---------- products ----------

def test_add_product_creates_size_variants(app, client, admin):
    with app.app_context():
        category_id = Category.query.first().id
    resp = client.post("/admin/products/add", data={
        "name": "New Tee", "description": "d", "price": "650",
        "category_id": category_id, "stock_M": "3", "stock_L": "2", "stock_XL": "1",
    })
    assert resp.status_code == 302
    with app.app_context():
        product = Product.query.filter_by(name="New Tee").one()
        assert product.price == 650
        assert product.get_total_stock() == 6


def test_edit_product_updates_fields_and_stock(app, client, admin, seeded, get_stock):
    with app.app_context():
        category_id = Category.query.first().id
    resp = client.post(f"/admin/products/{seeded['product_id']}/edit", data={
        "name": "Renamed", "description": "x", "price": "700",
        "category_id": category_id, "is_active": "on",
        "stock_M": "9", "stock_L": "0", "stock_XL": "0",
    })
    assert resp.status_code == 302
    with app.app_context():
        product = db.session.get(Product, seeded["product_id"])
        assert product.name == "Renamed"
        assert product.price == 700
    assert get_stock(seeded["product_id"]) == 9


def test_toggle_and_deactivate_product(app, client, admin, seeded):
    resp = client.post(f"/admin/products/{seeded['product_id']}/toggle")
    assert resp.get_json() == {"success": True, "is_active": False}

    client.post(f"/admin/products/{seeded['product_id']}/toggle")
    client.post(f"/admin/products/{seeded['product_id']}/deactivate")
    with app.app_context():
        assert db.session.get(Product, seeded["product_id"]).is_active is False


def test_cannot_delete_product_that_has_orders(app, client, admin, seeded):
    make_order(app, seeded)
    client.post(f"/admin/products/{seeded['product_id']}/delete")
    with app.app_context():
        assert db.session.get(Product, seeded["product_id"]) is not None


def test_delete_product_without_orders(app, client, admin, seeded):
    resp = client.post(f"/admin/products/{seeded['product_id']}/delete")
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(Product, seeded["product_id"]) is None
        assert ProductVariant.query.filter_by(product_id=seeded["product_id"]).count() == 0


# ---------- orders ----------

def test_admin_cancel_returns_stock_once(app, client, admin, seeded, get_stock):
    order_id = make_order(app, seeded, qty=2)
    assert get_stock(seeded["product_id"]) == 5

    client.post(f"/admin/orders/{order_id}/status", data={"status": "cancelled"})
    assert get_stock(seeded["product_id"]) == 7  # the 2 reserved units are back

    client.post(f"/admin/orders/{order_id}/status", data={"status": "cancelled"})
    assert get_stock(seeded["product_id"]) == 7  # cancelling again must not restock again


def test_delivered_sets_delivered_at(app, client, admin, seeded):
    order_id = make_order(app, seeded)
    client.post(f"/admin/orders/{order_id}/status", data={"status": "delivered"})
    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == "delivered"
        assert order.delivered_at is not None


def test_invalid_order_status_is_ignored(app, client, admin, seeded):
    order_id = make_order(app, seeded)
    client.post(f"/admin/orders/{order_id}/status", data={"status": "bogus"})
    with app.app_context():
        assert db.session.get(Order, order_id).status == "pending"


# ---------- refunds ----------

def test_update_refund_status(app, client, admin, seeded):
    order_id = make_order(app, seeded, status="delivered")
    with app.app_context():
        refund = RefundRequest(order_id=order_id, user_id=seeded["user_id"], reason="Too small")
        db.session.add(refund)
        db.session.commit()
        refund_id = refund.id

    resp = client.post(f"/admin/refunds/{refund_id}/status", data={"status": "approved"})
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(RefundRequest, refund_id).status == "approved"


# ---------- users ----------

def test_toggle_admin_on_other_user_but_not_self(app, client, admin, seeded):
    resp = client.post(f"/admin/users/{seeded['user_id']}/toggle-admin")
    assert resp.get_json()["is_admin"] is True

    resp = client.post(f"/admin/users/{admin['id']}/toggle-admin")
    assert resp.get_json()["is_admin"] is True  # unchanged, you cannot demote yourself


def test_delete_user_removes_their_orders(app, client, admin, seeded):
    order_id = make_order(app, seeded)
    resp = client.post(f"/admin/users/{seeded['user_id']}/delete")
    assert resp.get_json()["success"] is True
    with app.app_context():
        assert db.session.get(User, seeded["user_id"]) is None
        assert db.session.get(Order, order_id) is None


def test_cannot_delete_yourself_or_another_admin(app, client, admin, seeded):
    resp = client.post(f"/admin/users/{admin['id']}/delete")
    assert resp.status_code == 400

    client.post(f"/admin/users/{seeded['user_id']}/toggle-admin")  # make the buyer an admin
    resp = client.post(f"/admin/users/{seeded['user_id']}/delete")
    assert resp.status_code == 400