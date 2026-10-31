import re
from datetime import datetime, timedelta

from app import db
from app.models import DiscountCode, Order, RefundRequest, User


def test_discount_validation_rules(app):
    now = datetime.utcnow()

    def code(**overrides):
        fields = dict(code="X", discount_type="percent", value=10, min_subtotal=0,
                      max_uses=None, uses_count=0, is_active=True, expires_at=None)
        fields.update(overrides)
        return DiscountCode(**fields)

    assert code().is_valid(100) == (True, None)
    assert code(is_active=False).is_valid(100)[0] is False
    assert code(expires_at=now - timedelta(days=1)).is_valid(100)[0] is False
    assert code(max_uses=1, uses_count=1).is_valid(100)[0] is False
    assert code(min_subtotal=200).is_valid(100)[0] is False
    assert code(min_subtotal=200).is_valid(250)[0] is True


def test_discount_amounts():
    percent = DiscountCode(code="P", discount_type="percent", value=15)
    fixed = DiscountCode(code="F", discount_type="fixed", value=50)
    assert percent.calculate_discount(200) == 30.0
    assert fixed.calculate_discount(200) == 50
    assert fixed.calculate_discount(30) == 30  # never more than the subtotal


def test_order_refund_window():
    assert Order(delivered_at=None).refund_deadline() is None
    assert Order(delivered_at=None).refund_window_open() is False
    assert Order(delivered_at=datetime.utcnow() - timedelta(hours=47)).refund_window_open() is True
    assert Order(delivered_at=datetime.utcnow() - timedelta(hours=49)).refund_window_open() is False


def test_order_shipping_address_roundtrip_and_bad_data():
    order = Order()
    order.set_shipping_address({"street": "1 Test St"})
    assert order.get_shipping_address() == {"street": "1 Test St"}
    order.shipping_address = "not json"
    assert order.get_shipping_address() == {}
    order.shipping_address = None
    assert order.get_shipping_address() == {}


def test_generated_order_numbers_look_right():
    assert re.fullmatch(r"FRK-\d{8}", Order.generate_order_number())


def test_user_guest_flag_and_repr():
    assert User(username="g", email=None).is_guest is True
    assert User(username="real", email="r@example.com").is_guest is False
    assert "real" in repr(User(username="real"))


def test_active_refund_request_ignores_rejected(app, seeded, order_factory):
    order_id = order_factory(status="delivered")
    now = datetime.utcnow()
    with app.app_context():
        db.session.add(RefundRequest(order_id=order_id, user_id=seeded["user_id"],
                                     status="rejected", created_at=now - timedelta(days=2)))
        db.session.commit()
        order = db.session.get(Order, order_id)
        assert order.active_refund_request() is None

        db.session.add(RefundRequest(order_id=order_id, user_id=seeded["user_id"],
                                     status="pending", created_at=now))
        db.session.commit()
        db.session.refresh(order)
        assert order.active_refund_request().status == "pending"