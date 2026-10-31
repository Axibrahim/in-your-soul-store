import pytest


@pytest.mark.parametrize("path", [
    "/", "/shop", "/about", "/robots.txt", "/sitemap.xml", "/manifest.webmanifest", "/sw.js",
])
def test_public_pages_return_200(client, seeded, path):
    assert client.get(path).status_code == 200


def test_product_page_shows_product(client, seeded):
    resp = client.get(f"/product/{seeded['product_id']}")
    assert resp.status_code == 200
    assert b"Test Tee" in resp.data


def test_missing_product_is_404(client, seeded):
    assert client.get("/product/999999").status_code == 404


def test_security_headers_present(client):
    resp = client.get("/about")
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in resp.headers


def test_robots_blocks_private_areas_and_lists_sitemap(client):
    body = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /admin/" in body
    assert "Sitemap:" in body


def test_sitemap_lists_active_products(client, seeded):
    body = client.get("/sitemap.xml").get_data(as_text=True)
    assert f"/product/{seeded['product_id']}" in body