"""SEO plumbing: robots.txt, sitemap.xml, canonical URLs, noindex headers."""
import os
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request, url_for

from app import cache
from app.models import Product, Category

seo_bp = Blueprint('seo', __name__)

# Pages that must never appear in search results.
PRIVATE_PREFIXES = ('/admin', '/cart', '/account', '/auth', '/api', '/offline')


def site_url():
    """Canonical origin, e.g. https://www.inyoursoul.store (override with SITE_URL)."""
    return os.environ.get('SITE_URL', 'https://www.inyoursoul.store').rstrip('/')


def init_seo(app):
    """Hook SEO helpers into the app (context vars + X-Robots-Tag header)."""

    @app.context_processor
    def inject_seo():
        return {
            'site_url': site_url(),
            # Path only (query strings stripped) so tracking params never fragment the URL.
            'canonical_url': site_url() + request.path,
            # Private pages also get <meta name="robots" content="noindex">.
            'seo_noindex': request.path.startswith(PRIVATE_PREFIXES),
        }

    @app.after_request
    def add_robots_header(response):
        if request.path.startswith(PRIVATE_PREFIXES):
            response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response


@seo_bp.route('/robots.txt')
def robots():
    body = "\n".join([
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /cart/",
        "Disallow: /account/",
        "Disallow: /auth/",
        "Disallow: /api/",
        "Disallow: /*?*sort=",
        "Disallow: /*?*q=",
        "",
        f"Sitemap: {site_url()}/sitemap.xml",
        "",
    ])
    return Response(body, mimetype='text/plain')


@cache.cached(timeout=3600, key_prefix='sitemap_xml')
def _build_sitemap():
    base = site_url()
    urls = [
        (f"{base}/", [], 'daily', '1.0'),
        (f"{base}/shop", [], 'daily', '0.9'),
        (f"{base}/about", [], 'monthly', '0.5'),
    ]

    for cat in Category.query.all():
        urls.append((f"{base}/shop?category={cat.slug}", [], 'weekly', '0.7'))

    products = Product.query.filter_by(is_active=True).all()
    for p in products:
        images = [u for u in (p.image_url, p.image_url_2, p.image_url_3, p.image_url_4)
                  if u and u.startswith('http')]
        urls.append((f"{base}/product/{p.id}", images, 'weekly', '0.8'))

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for loc, images, freq, prio in urls:
        out.append('  <url>')
        out.append(f'    <loc>{escape(loc)}</loc>')
        out.append(f'    <changefreq>{freq}</changefreq>')
        out.append(f'    <priority>{prio}</priority>')
        for img in images:
            out.append(f'    <image:image><image:loc>{escape(img)}</image:loc></image:image>')
        out.append('  </url>')
    out.append('</urlset>')
    return "\n".join(out)


@seo_bp.route('/sitemap.xml')
def sitemap():
    return Response(_build_sitemap(), mimetype='application/xml')