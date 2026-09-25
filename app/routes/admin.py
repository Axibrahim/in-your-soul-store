from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import OrderItem, Product, ProductVariant, Category, Order, User, DiscountCode, db
from functools import wraps
import os, re, time, secrets
from app.email import send_order_status_email
from werkzeug.utils import secure_filename
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()  # lets Image.open() read iPhone .heic/.heif photos
from supabase import create_client, Client
from datetime import datetime, timedelta

admin_bp = Blueprint('admin', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'heic', 'heif'}
ALLOWED_PIL_FORMATS = {'PNG', 'JPEG', 'WEBP', 'GIF', 'HEIF'}

# Initialize Supabase Client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
BUCKET_NAME = "product-images"


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Access denied. Admin only.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def save_product_image(file, folder=None):
    """Validates and uploads an image to Supabase storage, returning its public URL.

    `folder` is an optional path prefix within BUCKET_NAME (e.g. "refunds") so
    refund evidence photos land in their own folder of the same bucket instead
    of needing a second bucket provisioned in Supabase.
    """
    if not file or not file.filename or not allowed_file(file.filename):
        return None

    try:
        image = Image.open(file.stream)
        image.verify()
        file.stream.seek(0)
        image = Image.open(file.stream)
        image_format = image.format
    except Exception:
        current_app.logger.warning("Image validation failed for %s", file.filename)
        return None

    if image_format not in ALLOWED_PIL_FORMATS:
        return None

    base = secure_filename(os.path.splitext(file.filename)[0]) or 'image'

    # HEIC/HEIF only renders natively in Safari - Chrome, Firefox and Edge (what
    # the admin dashboard actually runs in) can't display it in an <img> tag.
    # Re-encode to JPEG at upload time so it's viewable everywhere, rather than
    # storing the raw iPhone file.
    if image_format == 'HEIF':
        from io import BytesIO
        buf = BytesIO()
        image.convert('RGB').save(buf, format='JPEG', quality=90)
        file_bytes = buf.getvalue()
        ext = 'jpg'
    else:
        file.stream.seek(0)
        file_bytes = file.stream.read()
        ext = image_format.lower().replace('jpeg', 'jpg')

    filename = f"{base}_{int(time.time())}_{secrets.token_hex(4)}.{ext}"
    storage_path = f"{folder.strip('/')}/{filename}" if folder else filename

    content_type_map = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif'}
    content_type = content_type_map.get(ext, file.content_type or 'application/octet-stream')

    if not supabase:
        current_app.logger.error("Supabase client not configured — check SUPABASE_URL / SUPABASE_KEY env vars")
        return None

    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": "true"}
        )
        return supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    except Exception as e:
        current_app.logger.exception("Supabase upload failed for %s: %s", storage_path, e)
        return None


def delete_product_image(url):
    """Best-effort delete of a product photo from Supabase storage.

    Only ever called after the DB field pointing at it has already been
    cleared, so a failure here (network hiccup, file already gone) just
    means an orphaned file in the bucket - never blocks the save or leaves
    the product pointing at a missing image.
    """
    if not url or not supabase:
        return
    try:
        filename = url.rstrip('/').split('/')[-1]
        if filename:
            supabase.storage.from_(BUCKET_NAME).remove([filename])
    except Exception as e:
        current_app.logger.warning("Supabase delete failed for %s: %s", url, e)


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    total_products = Product.query.filter_by(is_active=True).count()
    total_users = User.query.count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    revenue = db.session.query(db.func.sum(Order.total)).filter(
        Order.status.in_(['confirmed', 'shipped', 'delivered'])
    ).scalar() or 0

    return render_template('admin/dashboard.html',
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           total_products=total_products,
                           total_users=total_users,
                           recent_orders=recent_orders,
                           revenue=revenue)


@admin_bp.route('/products')
@login_required
@admin_required
def products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@admin_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    categories = Category.query.all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = request.form.get('price', type=float)
        category_id = request.form.get('category_id', type=int)
        is_featured = request.form.get('is_featured') == 'on'

        if not name or not price:
            flash('Name and price are required.', 'danger')
            return render_template('admin/add_product.html', categories=categories)

        product = Product(
            name=name,
            description=description,
            price=price,
            category_id=category_id,
            is_featured=is_featured
        )

        image_fields = [
            ('image', 'image_url'),
            ('image2', 'image_url_2'),
            ('image3', 'image_url_3'),
            ('image4', 'image_url_4')
        ]
        for field_name, attr in image_fields:
            file = request.files.get(field_name)
            public_url = save_product_image(file)
            if public_url:
                setattr(product, attr, public_url)
            elif file and file.filename:
                flash(f'{field_name}: file was not a valid image or upload failed and was skipped.', 'danger')

        db.session.add(product)
        db.session.flush()

        sizes = ['M', 'L', 'XL']
        for size in sizes:
            stock = request.form.get(f'stock_{size}', 0, type=int)
            if stock >= 0:
                variant = ProductVariant(product_id=product.id, size=size, stock=stock)
                db.session.add(variant)

        db.session.commit()
        flash(f'Product "{name}" added successfully.', 'success')
        return redirect(url_for('admin.products'))

    return render_template('admin/add_product.html', categories=categories)


@admin_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.all()

    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.price = request.form.get('price', type=float)
        product.category_id = request.form.get('category_id', type=int)
        product.is_featured = request.form.get('is_featured') == 'on'
        product.is_active = request.form.get('is_active') == 'on'

        image_fields = [
            ('image', 'image_url'),
            ('image2', 'image_url_2'),
            ('image3', 'image_url_3'),
            ('image4', 'image_url_4')
        ]
        for field_name, attr in image_fields:
            file = request.files.get(field_name)
            public_url = save_product_image(file)
            if public_url:
                # a new upload replaces whatever was there, delete checkbox or not
                delete_product_image(getattr(product, attr))
                setattr(product, attr, public_url)
            elif file and file.filename:
                flash(
                    f'{field_name}: file was not a valid image or upload failed and was skipped.',
                    'danger'
                )
            elif request.form.get(f'delete_{field_name}') == 'on':
                delete_product_image(getattr(product, attr))
                setattr(product, attr, None)

        # Default sizes: M, L, XL
        for size in ['M', 'L', 'XL']:
            stock = request.form.get(f'stock_{size}', 0, type=int)

            variant = ProductVariant.query.filter_by(
                product_id=product.id,
                size=size
            ).first()

            if variant:
                variant.stock = max(0, stock)
            else:
                db.session.add(
                    ProductVariant(
                        product_id=product.id,
                        size=size,
                        stock=max(0, stock)
                    )
                )

        # Optional sizes: XS, S, XXL, XXXL
        for size in ['XS', 'S', 'XXL', 'XXXL']:
            variant = ProductVariant.query.filter_by(
                product_id=product.id,
                size=size
            ).first()

            enabled = request.form.get(f'enable_{size}') == 'on'

            if enabled:
                stock = request.form.get(f'stock_{size}', 0, type=int)

                if variant:
                    variant.stock = max(0, stock)
                else:
                    db.session.add(
                        ProductVariant(
                            product_id=product.id,
                            size=size,
                            stock=max(0, stock)
                        )
                    )

            elif variant:
                # Hide optional size without deleting the variant
                variant.stock = 0

        db.session.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('admin.products'))

    return render_template(
        'admin/edit_product.html',
        product=product,
        categories=categories
    )


@admin_bp.route('/products/<int:product_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_product(product_id):
    product = Product.query.get_or_404(product_id)

    product.is_active = False
    db.session.commit()

    flash(f'Product "{product.name}" deactivated.', 'success')
    return redirect(url_for('admin.products'))


@admin_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    # Do not permanently delete products that are already part of orders
    if OrderItem.query.filter_by(product_id=product.id).first():
        flash(
            'This product cannot be permanently deleted because it is linked to existing orders. '
            'Deactivate it instead.',
            'danger'
        )
        return redirect(url_for('admin.products'))

    # Delete product variants first
    ProductVariant.query.filter_by(product_id=product.id).delete(
        synchronize_session=False
    )

    # Delete the product
    db.session.delete(product)
    db.session.commit()

    flash(f'Product "{product.name}" permanently deleted.', 'success')
    return redirect(url_for('admin.products'))


@admin_bp.route('/products/<int:product_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': product.is_active})


@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    status_filter = request.args.get('status', None)
    query = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    orders = query.all()
    return render_template('admin/orders.html', orders=orders, status_filter=status_filter)


@admin_bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/order_detail.html', order=order)


@admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    valid = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled']
    if new_status in valid:
        old_status = order.status
        order.status = new_status
        if new_status == 'delivered' and old_status != 'delivered':
            # Marks the start of the 48h refund window. Guarded so re-submitting
            # the same "delivered" status twice in a row doesn't reset the
            # clock - but a genuine re-delivery (delivered -> cancelled ->
            # delivered again) does restart it, which is correct.
            order.delivered_at = datetime.utcnow()
        db.session.commit()
        flash(f'Order status updated to {new_status}.', 'success')

        # Only email on a genuine change into a customer-meaningful status
        if new_status != old_status and new_status in ('shipped', 'delivered', 'cancelled', 'confirmed'):
            customer = User.query.get(order.user_id)
            if customer and customer.email:
                send_order_status_email(customer.email, order.order_number, new_status, first_name=customer.first_name)
    return redirect(url_for('admin.order_detail', order_id=order_id))


@admin_bp.route('/refunds')
@login_required
@admin_required
def refunds():
    from app.models import RefundRequest
    status_filter = request.args.get('status', None)
    query = RefundRequest.query.order_by(RefundRequest.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)
    requests_list = query.all()
    return render_template('admin/refunds.html', requests=requests_list, status_filter=status_filter)


@admin_bp.route('/refunds/<int:request_id>/status', methods=['POST'])
@login_required
@admin_required
def update_refund_status(request_id):
    from app.models import RefundRequest
    from app.email import send_refund_status_email
    refund = RefundRequest.query.get_or_404(request_id)
    new_status = request.form.get('status')
    if new_status in ('pending', 'approved', 'rejected'):
        old_status = refund.status
        refund.status = new_status
        db.session.commit()
        flash(f'Refund request marked {new_status}.', 'success')

        # Only email on a genuine decision, not a no-op re-save
        if new_status != old_status and new_status in ('approved', 'rejected'):
            customer = refund.user
            if customer and customer.email:
                send_refund_status_email(customer.email, refund.order, refund, first_name=customer.first_name)
    return redirect(url_for('admin.refunds', status=request.form.get('return_filter') or None))


@admin_bp.route('/categories')
@login_required
@admin_required
def categories():
    cats = Category.query.all()
    return render_template('admin/categories.html', categories=cats)


@admin_bp.route('/categories/add', methods=['POST'])
@login_required
@admin_required
def add_category():
    name = request.form.get('name', '').strip()
    if name:
        slug = slugify(name)
        if not Category.query.filter_by(slug=slug).first():
            cat = Category(name=name, slug=slug)
            db.session.add(cat)
            db.session.commit()
            flash(f'Category "{name}" added.', 'success')
        else:
            flash('Category already exists.', 'danger')
    return redirect(url_for('admin.categories'))


@admin_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted.', 'success')
    return redirect(url_for('admin.categories'))


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/<int:user_id>/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id != current_user.id:
        user.is_admin = not user.is_admin
        db.session.commit()
    return jsonify({'success': True, 'is_admin': user.is_admin})


@admin_bp.route('/discounts')
@login_required
@admin_required
def discounts():
    codes = DiscountCode.query.order_by(DiscountCode.created_at.desc()).all()
    return render_template('admin/discounts.html', codes=codes)


@admin_bp.route('/discounts/add', methods=['POST'])
@login_required
@admin_required
def add_discount():
    code = request.form.get('code', '').strip().upper()
    discount_type = request.form.get('discount_type', 'percent')
    value = request.form.get('value', type=float)
    min_subtotal = request.form.get('min_subtotal', 0, type=float)
    max_uses = request.form.get('max_uses', type=int)
    expires_days = request.form.get('expires_days', type=int)

    if not code or not value or discount_type not in ('percent', 'fixed'):
        flash('Code and value are required.', 'danger')
        return redirect(url_for('admin.discounts'))

    if DiscountCode.query.filter_by(code=code).first():
        flash('A discount code with that name already exists.', 'danger')
        return redirect(url_for('admin.discounts'))

    if discount_type == 'percent' and (value <= 0 or value > 100):
        flash('Percent discounts must be between 1 and 100.', 'danger')
        return redirect(url_for('admin.discounts'))

    if value <= 0:
        flash('Value must be greater than 0.', 'danger')
        return redirect(url_for('admin.discounts'))

    expires_at = datetime.utcnow() + timedelta(days=expires_days) if expires_days else None

    dc = DiscountCode(
        code=code,
        discount_type=discount_type,
        value=value,
        min_subtotal=min_subtotal or 0,
        max_uses=max_uses,
        expires_at=expires_at
    )
    db.session.add(dc)
    db.session.commit()
    flash(f'Discount code "{code}" created.', 'success')
    return redirect(url_for('admin.discounts'))


@admin_bp.route('/discounts/<int:discount_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_discount(discount_id):
    dc = DiscountCode.query.get_or_404(discount_id)
    dc.is_active = not dc.is_active
    db.session.commit()
    flash(f'"{dc.code}" is now {"active" if dc.is_active else "disabled"}.', 'success')
    return redirect(url_for('admin.discounts'))


@admin_bp.route('/discounts/<int:discount_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_discount(discount_id):
    dc = DiscountCode.query.get_or_404(discount_id)
    db.session.delete(dc)
    db.session.commit()
    flash('Discount code deleted.', 'success')
    return redirect(url_for('admin.discounts'))