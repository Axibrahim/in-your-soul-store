import pytest

from app import cache, create_app, db
from app.models import Category, Product, ProductVariant, User

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