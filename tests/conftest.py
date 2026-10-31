import pytest
from flask import template_rendered

from app import cache, create_app, db
from app.models import Category, Order, OrderItem, Product, ProductVariant, User

PASSWORD = "Passw0rd!x1"


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        cache.clear()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()  # closes the in-memory SQLite connection


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded(app):
    """One category, one product (size M, stock 5, price 500) and one verified user."""
    with app.app_context():
        category = Category(name="Hoodies", slug="hoodies")
        db.session.add(category)
        db.session.flush()

        product = Product(
            name="Test Tee",
            description="A test product",
            price=500.0,
            category_id=category.id,
            is_active=True,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(ProductVariant(product_id=product.id, size="M", stock=5))

        user = User(
            username="buyer",
            email="buyer@example.com",
            first_name="Test",
            last_name="Buyer",
            phone="01000000000",
            email_verified=True,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()

        return {
            "product_id": product.id,
            "user_id": user.id,
            "email": "buyer@example.com",
            "password": PASSWORD,
        }


@pytest.fixture()
def login(client):
    def _login(email, password=PASSWORD):
        return client.post("/auth/login", data={"email": email, "password": password})
    return _login


@pytest.fixture()
def add_to_cart(client):
    def _add(product_id, quantity=1, size="M"):
        return client.post(
            "/cart/add",
            data={"product_id": product_id, "size": size, "quantity": quantity},
        )
    return _add


@pytest.fixture()
def get_stock(app):
    def _get(product_id, size="M"):
        with app.app_context():
            return ProductVariant.query.filter_by(product_id=product_id, size=size).first().stock
    return _get

@pytest.fixture()
def other_user(app):
    """A second, unrelated verified customer."""
    with app.app_context():
        user = User(
            username="other", email="other@example.com", first_name="Other",
            last_name="Person", phone="01000000002", email_verified=True,
        )
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        return {"id": user.id, "email": "other@example.com", "password": PASSWORD}


@pytest.fixture()
def order_factory(app, seeded):
    """Create an order with one item (size M). Stock is NOT deducted here."""
    counter = {"n": 100}

    def _make(status="pending", qty=2, user_id=None, payment_method="cod",
              payment_status="unpaid", delivered_at=None, payment_deadline=None):
        counter["n"] += 1
        with app.app_context():
            pid = seeded["product_id"]
            variant = ProductVariant.query.filter_by(product_id=pid, size="M").first()
            order = Order(
                order_number=f"FRK-{counter['n']:08d}",
                user_id=user_id or seeded["user_id"],
                payment_method=payment_method,
                payment_status=payment_status,
                status=status,
                subtotal=500 * qty,
                total=500 * qty,
                delivered_at=delivered_at,
                payment_deadline=payment_deadline,
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

    return _make


@pytest.fixture()
def rendered(app):
    """Records (template_name, context) for every template rendered, so tests
    can check what a route passed to its template without parsing HTML."""
    records = []

    def _record(sender, template, context, **extra):
        records.append((template.name, dict(context)))

    template_rendered.connect(_record, app)
    yield records
    template_rendered.disconnect(_record, app)