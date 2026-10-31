from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Category, Order, Product, ProductVariant
from app.routes import main


def add_product(app, name, price=500.0, category_id=None, is_active=True,
                is_featured=False, stock=5, image_url=None):
    with app.app_context():
        if category_id is None:
            category_id = Category.query.first().id
        product = Product(name=name, description="d", price=price, category_id=category_id,
                          is_active=is_active, is_featured=is_featured, image_url=image_url)
        db.session.add(product)
        db.session.flush()
        db.session.add(ProductVariant(product_id=product.id, size="M", stock=stock))
        db.session.commit()
        return product.id


def context_for(rendered, template_name):
    return next(ctx for name, ctx in rendered if name == template_name)


def shop_names(ctx):
    return [p.name for p in ctx["products"].items]


# ---------- shop listing ----------

def test_shop_sorting_by_price(app, client, seeded, rendered):
    add_product(app, "Black Hoodie", price=900)
    client.get("/shop?sort=price_desc")
    assert shop_names(context_for(rendered, "main/shop.html")) == ["Black Hoodie", "Test Tee"]
    rendered.clear()
    client.get("/shop?sort=price_asc")
    assert shop_names(context_for(rendered, "main/shop.html")) == ["Test Tee", "Black Hoodie"]


def test_shop_search_is_case_insensitive(app, client, seeded, rendered):
    add_product(app, "Black Hoodie", price=900)
    client.get("/shop?q=hood")
    assert shop_names(context_for(rendered, "main/shop.html")) == ["Black Hoodie"]


def test_shop_category_filter(app, client, seeded, rendered):
    with app.app_context():
        tees = Category(name="Tees", slug="tees")
        db.session.add(tees)
        db.session.commit()
        tees_id = tees.id
    add_product(app, "Plain Tee", category_id=tees_id)
    client.get("/shop?category=tees")
    assert shop_names(context_for(rendered, "main/shop.html")) == ["Plain Tee"]


def test_shop_hides_inactive_products(app, client, seeded, rendered):
    add_product(app, "Hidden", is_active=False)
    client.get("/shop")
    assert "Hidden" not in shop_names(context_for(rendered, "main/shop.html"))


def test_shop_seo_flags_and_canonical(app, client, seeded, rendered, monkeypatch):
    monkeypatch.setenv("SITE_URL", "https://shop.example.com")

    client.get("/shop")
    ctx = context_for(rendered, "main/shop.html")
    assert ctx["seo_noindex"] is False
    assert ctx["canonical_url"] == "https://shop.example.com/shop"

    rendered.clear()
    client.get("/shop?category=hoodies&page=2")
    ctx = context_for(rendered, "main/shop.html")
    assert ctx["canonical_url"] == "https://shop.example.com/shop?category=hoodies&page=2"

    for noindex_url in ("/shop?sort=price_asc", "/shop?q=tee", "/shop?category=does-not-exist"):
        rendered.clear()
        client.get(noindex_url)
        assert context_for(rendered, "main/shop.html")["seo_noindex"] is True, noindex_url


def test_shop_page_beyond_the_last_is_still_200(client, seeded):
    assert client.get("/shop?page=99").status_code == 200


# ---------- homepage ----------

def test_homepage_shows_featured_products_in_latest_hits(app, client, seeded, rendered):
    add_product(app, "Star Piece", is_featured=True)
    client.get("/")
    names = [p.name for p in context_for(rendered, "main/index.html")["latest_products"]]
    assert names == ["Star Piece"]


def test_homepage_checks_expired_orders_at_most_once_a_minute(client, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "cancel_expired_orders", lambda: calls.append(1))
    main._last_expired_check["at"] = None
    client.get("/")
    client.get("/")
    assert len(calls) == 1


def test_homepage_survives_a_failure_in_expired_order_cleanup(client, monkeypatch):
    def boom():
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(main, "cancel_expired_orders", boom)
    main._last_expired_check["at"] = None
    assert client.get("/").status_code == 200


def test_homepage_cancels_expired_unpaid_orders(app, client, seeded, order_factory, get_stock):
    order_id = order_factory(payment_method="instapay", payment_status="unpaid", status="pending",
                             payment_deadline=datetime.utcnow() - timedelta(hours=1), qty=2)
    main._last_expired_check["at"] = None
    client.get("/")
    with app.app_context():
        assert db.session.get(Order, order_id).status == "cancelled"
    assert get_stock(seeded["product_id"]) == 7


def test_unexpired_and_cod_orders_are_left_alone(app, client, seeded, order_factory):
    waiting = order_factory(payment_method="instapay", payment_deadline=datetime.utcnow() + timedelta(hours=1))
    cod = order_factory(payment_method="cod")
    main._last_expired_check["at"] = None
    client.get("/")
    with app.app_context():
        assert db.session.get(Order, waiting).status == "pending"
        assert db.session.get(Order, cod).status == "pending"


# ---------- product page ----------

def test_product_page_structured_data(app, client, seeded, rendered, monkeypatch):
    monkeypatch.setenv("SITE_URL", "https://shop.example.com")
    product_id = add_product(app, "Photo Tee", image_url="https://img.example/a.jpg")
    assert client.get(f"/product/{product_id}").status_code == 200

    ctx = context_for(rendered, "main/product_detail.html")
    ld = ctx["product_ld"]
    assert ld["name"] == "Photo Tee"
    assert ld["image"] == ["https://img.example/a.jpg"]
    assert ld["category"] == "Hoodies"
    assert ld["offers"]["url"] == f"https://shop.example.com/product/{product_id}"
    assert ld["offers"]["availability"].endswith("InStock")
    crumbs = [c["name"] for c in ctx["breadcrumb_ld"]["itemListElement"]]
    assert crumbs == ["Home", "Shop", "Photo Tee"]


def test_out_of_stock_product_is_marked_out_of_stock(app, client, seeded, rendered):
    product_id = add_product(app, "Sold Out Tee", stock=0)
    client.get(f"/product/{product_id}")
    ld = context_for(rendered, "main/product_detail.html")["product_ld"]
    assert ld["offers"]["availability"].endswith("OutOfStock")


def test_inactive_product_is_404_for_visitors(app, client, seeded):
    product_id = add_product(app, "Old Drop", is_active=False)
    assert client.get(f"/product/{product_id}").status_code == 404


# ---------- JSON API and best sellers ----------

def test_api_products_lists_only_active_products(app, client, seeded):
    add_product(app, "Hidden", is_active=False)
    data = client.get("/api/products").get_json()
    assert [p["name"] for p in data] == ["Test Tee"]
    assert data[0]["stock"] == 5


def test_top_selling_products(app, seeded, order_factory):
    with app.app_context():
        assert main._get_top_selling_products() == []

    order_factory(status="pending", qty=3)
    with app.app_context():
        assert [p.name for p in main._get_top_selling_products()] == ["Test Tee"]


def test_cancelled_orders_do_not_count_as_best_sellers(app, seeded, order_factory):
    order_factory(status="cancelled", qty=3)
    with app.app_context():
        assert main._get_top_selling_products() == []