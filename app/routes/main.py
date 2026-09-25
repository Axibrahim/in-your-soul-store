import os
from flask import Blueprint, render_template, request, jsonify, session, current_app
from app.models import Product, Category, db
from app import cache
from datetime import datetime, timedelta
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy import func
from flask_sqlalchemy.pagination import Pagination

main_bp = Blueprint('main', __name__)

# In-memory timestamp guard so cancel_expired_orders() runs at most once every
# 60s per worker process, instead of on every single hit to '/'. It was
# previously running (and writing to the DB) on every homepage request, which
# under load competes for the same handful of Supabase pooler connections as
# every other query on the site for no real benefit — orders don't need to be
# cancelled within milliseconds of expiring, once a minute is plenty.
_last_expired_check = {"at": None}


# NOTE: we deliberately cache only these data-fetching helpers (via
# cache.memoize), never the rendered response itself (cache.cached). The
# pages below embed session-specific content in the shared base template —
# the CSRF token meta tag, cart count, login state — so caching a fully
# rendered HTML response would leak one visitor's session data (including
# their CSRF token) to every other visitor for the cache's lifetime, breaking
# their form submissions and leaking session state. Caching the DB query
# results instead gets the same reduction in Supabase load with none of that
# risk, since render_template() still runs fresh on every request using the
# current visitor's own session.
#
# IMPORTANT: any relationship a template accesses on a cached object (e.g.
# product.variants via get_total_stock(), product.category) must be
# eager-loaded here with selectinload/joinedload. Once these objects are
# cached, their original DB session is gone — a lazy-load attempt later
# raises DetachedInstanceError instead of quietly querying.

@cache.memoize(timeout=30)
def _get_homepage_products():
    all_products = Product.query.options(selectinload(Product.variants)).filter_by(is_active=True).order_by(Product.created_at.desc()).limit(12).all()
    categories = Category.query.all()
    return all_products, categories


def _get_top_selling_products(limit=8):
    """Best-sellers fallback for Latest Hits: active products ranked by total
    units sold across every non-cancelled order (any payment/status besides
    'cancelled' still counts - an unpaid COD order still reflects real demand).
    Products that have never sold don't show up here at all.
    """
    from app.models import Order, OrderItem
    rows = (
        db.session.query(OrderItem.product_id, func.sum(OrderItem.quantity).label('sold'))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Order.status != 'cancelled')
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []
    ids_in_rank_order = [r.product_id for r in rows]
    by_id = {
        p.id: p
        for p in Product.query.options(selectinload(Product.variants))
        .filter(Product.id.in_(ids_in_rank_order), Product.is_active == True)
        .all()
    }
    # keep best-seller rank order; skip any that got deactivated since they sold
    return [by_id[pid] for pid in ids_in_rank_order if pid in by_id]


@cache.memoize(timeout=30)
def _get_latest_products():
    """The 'Latest Hits' swipe carousel (latest_products).

    Shows exactly the products ticked "Show in Latest Hits" in the admin
    panel (that checkbox is the existing is_featured column, just
    relabelled - no DB change). No auto-padding with best-sellers or
    newest arrivals, and no min/max count - admins are fully in control
    of how many (or how few) cards appear here.
    """
    return (
        Product.query.options(selectinload(Product.variants))
        .filter_by(is_active=True, is_featured=True)
        .order_by(Product.created_at.desc())
        .all()
    )


_latest_bg_cache = {}


def _get_latest_bg():
    """Optional background for the Latest Hits section.

    Drop a file into app/static and redeploy - no code or DB change needed:
      videos/latest-hits.mp4                       looping muted video
      images/latest-hits-bg.(jpg|png|webp)         photo (also the video poster)
    Neither present = the logo is shown faintly instead. Checked once per worker.
    """
    if 'bg' not in _latest_bg_cache:
        static_dir = current_app.static_folder

        def found(*candidates):
            for rel in candidates:
                if os.path.isfile(os.path.join(static_dir, rel)):
                    return rel
            return None

        _latest_bg_cache['bg'] = {
            'video': found('videos/latest-hits.mp4'),
            'image': found('images/latest-hits-bg.jpg', 'images/latest-hits-bg.png', 'images/latest-hits-bg.webp'),
        }
    return _latest_bg_cache['bg']


@main_bp.route('/')
def index():
    _maybe_cancel_expired_orders()
    all_products, categories = _get_homepage_products()
    return render_template('main/index.html',
                           products=all_products,
                           categories=categories,
                           latest_products=_get_latest_products(),
                           latest_bg=_get_latest_bg())


class _ShopPage(Pagination):
    """Pagination rebuilt from plain cached data.

    query.paginate() returns an object that holds the live query + DB session,
    which can't be pickled - so it can't go into the cache (that is what made
    /shop raise "Can't pickle Session" -> HTTP 500). We cache only the picklable
    parts (items + numbers) and rebuild this object on every request. It keeps
    every property shop.html uses: items, total, pages, page, has_prev/has_next,
    prev_num/next_num and iter_pages().
    """

    def __init__(self, page, per_page, items, total):
        self.page = page
        self.per_page = per_page
        self.max_per_page = None
        self.error_out = False
        self.items = items
        self.total = total
        self._query_args = {}

    def _query_items(self):
        return self.items

    def _query_count(self):
        return self.total


@cache.memoize(timeout=30)
def _get_shop_products(page, category_slug, sort, search):
    query = Product.query.options(selectinload(Product.variants)).filter_by(is_active=True)

    if category_slug:
        cat = Category.query.filter_by(slug=category_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    pg = query.paginate(page=page, per_page=12, error_out=False)
    categories = Category.query.all()
    # plain, picklable data only - never the Pagination object itself
    return pg.items, pg.page, pg.per_page, pg.total, categories


@main_bp.route('/shop')
def shop():
    page = request.args.get('page', 1, type=int)
    category_slug = request.args.get('category', None)
    sort = request.args.get('sort', 'new')
    search = request.args.get('q', None)

    items, pg_page, pg_per_page, pg_total, categories = _get_shop_products(page, category_slug, sort, search)
    products = _ShopPage(pg_page, pg_per_page, items, pg_total)

    return render_template('main/shop.html',
                           products=products,
                           categories=categories,
                           current_category=category_slug,
                           sort=sort,
                           search=search,
                           latest_products=_get_latest_products(),
                           latest_bg=_get_latest_bg())


@cache.memoize(timeout=30)
def _get_product_detail(product_id):
    product = Product.query.options(
        selectinload(Product.variants), joinedload(Product.category)
    ).filter_by(id=product_id).first_or_404()
    related = Product.query.filter_by(
        category_id=product.category_id,
        is_active=True
    ).filter(Product.id != product_id).limit(4).all()
    return product, related


@main_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product, related = _get_product_detail(product_id)
    return render_template('main/product_detail.html', product=product, related=related)


@main_bp.route('/about')
def about():
    return render_template('main/about.html')


@main_bp.route('/api/products')
@cache.cached(timeout=30)  # pure JSON, no session/CSRF content — safe to cache the full response
def api_products():
    products = Product.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'image_url': p.image_url,
        'stock': p.get_total_stock()
    } for p in products])



def _maybe_cancel_expired_orders():
    now = datetime.utcnow()
    last = _last_expired_check["at"]
    if last is not None and now - last < timedelta(seconds=60):
        return
    _last_expired_check["at"] = now
    cancel_expired_orders()


def cancel_expired_orders():
    from app.models import Order, ProductVariant
    expired = Order.query.filter(
        Order.payment_method.in_(['vodafone_cash', 'instapay']),
        Order.payment_status == 'unpaid',
        Order.status == 'pending',
        Order.payment_deadline < datetime.utcnow()
    ).all()
    for order in expired:
        order.status = 'cancelled'
        for item in order.items:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                variant.stock += item.quantity
    if expired:
        db.session.commit()