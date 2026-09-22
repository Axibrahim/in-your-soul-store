from datetime import datetime, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app.models import Product, ProductVariant, Order, OrderItem, Address, DiscountCode, db
from app import limiter

cart_bp = Blueprint('cart', __name__)

DELIVERY_FEE = 80


def get_cart():
    return session.get('cart', {})


def save_cart(cart):
    session['cart'] = cart
    session.modified = True


def compute_subtotal(cart):
    items = []
    subtotal = 0
    for key, item in cart.items():
        product = Product.query.get(item['product_id'])
        if product:
            total = product.price * item['quantity']
            subtotal += total
            items.append({
                'key': key,
                'product': product,
                'size': item['size'],
                'quantity': item['quantity'],
                'total': total
            })
    return items, subtotal


def get_applied_discount(subtotal):
    """Returns (discount_obj_or_None, discount_amount, error_message_or_None).
    Clears an invalid/stale code from the session automatically."""
    code = session.get('discount_code')
    if not code:
        return None, 0, None

    discount = DiscountCode.query.filter_by(code=code).first()
    if not discount:
        session.pop('discount_code', None)
        session.modified = True
        return None, 0, None

    valid, error = discount.is_valid(subtotal)
    if not valid:
        session.pop('discount_code', None)
        session.modified = True
        return None, 0, error

    return discount, discount.calculate_discount(subtotal), None


@cart_bp.route('/')
def view_cart():
    cart = get_cart()
    items, subtotal = compute_subtotal(cart)
    discount, discount_amount, discount_error = get_applied_discount(subtotal)
    if discount_error:
        flash(discount_error, 'danger')

    shipping = 0 if subtotal >= 1500 else DELIVERY_FEE
    total = max(subtotal + shipping - discount_amount, 0)

    return render_template('main/cart.html',
                           items=items, subtotal=subtotal, shipping=shipping,
                           total=total, discount=discount, discount_amount=discount_amount)


@cart_bp.route('/add', methods=['POST'])
@limiter.limit("30 per minute")       # prevents cart spam bots
def add_to_cart():
    product_id = request.form.get('product_id', type=int)
    size = request.form.get('size', '')
    quantity = request.form.get('quantity', 1, type=int)

    if not product_id or not size:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'}), 404

    variant = ProductVariant.query.filter_by(product_id=product_id, size=size).first()
    if not variant or variant.stock < quantity:
        return jsonify({'success': False, 'message': 'Size unavailable or insufficient stock'}), 400

    cart = get_cart()
    key = f"{product_id}_{size}"

    if key in cart:
        new_qty = cart[key]['quantity'] + quantity
        if new_qty > variant.stock:
            return jsonify({'success': False, 'message': 'Not enough stock'}), 400
        cart[key]['quantity'] = new_qty
    else:
        cart[key] = {
            'product_id': product_id,
            'size': size,
            'quantity': quantity
        }

    save_cart(cart)
    cart_count = sum(i['quantity'] for i in cart.values())
    return jsonify({'success': True, 'message': 'Added to cart', 'cart_count': cart_count})


@cart_bp.route('/update', methods=['POST'])
def update_cart():
    key = request.form.get('key', '')
    quantity = request.form.get('quantity', 1, type=int)
    cart = get_cart()

    if key in cart:
        if quantity <= 0:
            del cart[key]
        else:
            item = cart[key]
            variant = ProductVariant.query.filter_by(
                product_id=item['product_id'],
                size=item['size']
            ).first()
            max_stock = variant.stock if variant else 0

            if quantity > max_stock:
                flash(f'Only {max_stock} in stock — quantity capped.', 'danger')
                quantity = max_stock

            if quantity <= 0:
                del cart[key]
            else:
                cart[key]['quantity'] = quantity
        save_cart(cart)

    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove', methods=['POST'])
def remove_from_cart():
    key = request.form.get('key', '')
    cart = get_cart()
    if key in cart:
        del cart[key]
        save_cart(cart)
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/count')
def cart_count():
    cart = get_cart()
    count = sum(i['quantity'] for i in cart.values())
    return jsonify({'count': count})



@cart_bp.route('/apply-discount', methods=['POST'])
@limiter.limit("15 per minute")       # prevents brute-forcing codes
def apply_discount():
    code = request.form.get('code', '').strip().upper()
    next_page = request.form.get('next', 'cart')
    redirect_target = 'cart.checkout' if next_page == 'checkout' else 'cart.view_cart'

    if not code:
        flash('Please enter a discount code.', 'danger')
        return redirect(url_for(redirect_target))

    cart = get_cart()
    _, subtotal = compute_subtotal(cart)

    discount = DiscountCode.query.filter_by(code=code).first()
    if not discount:
        flash('Invalid discount code.', 'danger')
        return redirect(url_for(redirect_target))

    valid, error = discount.is_valid(subtotal)
    if not valid:
        flash(error, 'danger')
        return redirect(url_for(redirect_target))

    session['discount_code'] = discount.code
    session.modified = True
    flash(f'Code "{discount.code}" applied.', 'success')
    return redirect(url_for(redirect_target))



@cart_bp.route('/remove-discount', methods=['POST'])
def remove_discount():
    next_page = request.form.get('next', 'cart')
    redirect_target = 'cart.checkout' if next_page == 'checkout' else 'cart.view_cart'
    session.pop('discount_code', None)
    session.modified = True
    return redirect(url_for(redirect_target))


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")       # prevents checkout abuse
def checkout():
    cart = get_cart()
    if not cart:
        flash('Your cart is empty.', 'info')
        return redirect(url_for('cart.view_cart'))

    items, subtotal = compute_subtotal(cart)
    shipping = 0 if subtotal >= 1500 else DELIVERY_FEE

    if request.method == 'POST':
        # Re-validate the discount right before placing the order, so a code
        # that expired / hit its cap between page-load and submit is caught.
        discount, discount_amount, discount_error = get_applied_discount(subtotal)
        if discount_error:
            flash(discount_error, 'danger')
            return redirect(url_for('cart.checkout'))

        grand_total = max(subtotal + shipping - discount_amount, 0)

        payment_method = request.form.get('payment_method', 'cod')

        # Whitelist payment methods
        if payment_method not in ('cod', 'vodafone_cash', 'instapay'):
            flash('Invalid payment method.', 'danger')
            return redirect(url_for('cart.checkout'))

        address_id = request.form.get('address_id', type=int)
        notes = request.form.get('notes', '').strip()

               # Manual address fields
        street = request.form.get('street', '').strip()
        building = request.form.get('building', '').strip()
        floor = request.form.get('floor', '').strip()
        apartment = request.form.get('apartment', '').strip()
        landmark = request.form.get('landmark', '').strip()
        district = request.form.get('district', '').strip()
        governorate = request.form.get('governorate', '').strip()

        used_new_address = False

        if address_id:
            addr = Address.query.filter_by(id=address_id, user_id=current_user.id).first()
            if addr:
                addr_data = {
                    'street': addr.street, 'building': addr.building, 'floor': addr.floor,
                    'apartment': addr.apartment, 'landmark': addr.landmark,
                    'district': addr.district, 'governorate': addr.governorate,
                }
            else:
                flash('Invalid address.', 'danger')
                return redirect(url_for('cart.checkout'))
        elif all([street, building, floor, district, governorate]):
            addr_data = {
                'street': street, 'building': building, 'floor': floor,
                'apartment': apartment or None, 'landmark': landmark or None,
                'district': district, 'governorate': governorate,
            }
            used_new_address = True
        else:
            flash('Please provide a complete shipping address (street, building and floor are required).', 'danger')
            return redirect(url_for('cart.checkout'))

        # Validate stock
        for item_data in items:
            variant = ProductVariant.query.filter_by(
                product_id=item_data['product'].id,
                size=item_data['size']
            ).first()
            if not variant or variant.stock < item_data['quantity']:
                flash(f"Insufficient stock for {item_data['product'].name} ({item_data['size']}).", 'danger')
                return redirect(url_for('cart.checkout'))

        # Create order
        order = Order(
            order_number=Order.generate_order_number(),
            user_id=current_user.id,
            payment_method=payment_method,
            subtotal=subtotal,
            shipping_cost=shipping,
            discount_code=discount.code if discount else None,
            discount_amount=discount_amount,
            total=grand_total,
            notes=notes
        )
        order.set_shipping_address(addr_data)

        # Set 2-hour payment deadline for online payment methods
        if payment_method in ('vodafone_cash', 'instapay'):
            order.payment_deadline = datetime.utcnow() + timedelta(hours=2)

        db.session.add(order)
        db.session.flush()

        
        # Auto-save a manually-typed address to the customer's address book,
        # so they don't have to retype it next time.
        if used_new_address:
            saved_addr = Address(
                user_id=current_user.id,
                label='Home',
                street=addr_data['street'],
                building=addr_data['building'],
                floor=addr_data['floor'],
                apartment=addr_data.get('apartment'),
                landmark=addr_data.get('landmark'),
                district=addr_data['district'],
                governorate=addr_data['governorate'],
                is_default=not current_user.addresses,  # first address becomes default automatically
            )
            db.session.add(saved_addr)

        # Create order items and reduce stock
        for item_data in items:
            variant = ProductVariant.query.filter_by(
                product_id=item_data['product'].id,
                size=item_data['size']
            ).first()
            variant.stock -= item_data['quantity']

            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data['product'].id,
                variant_id=variant.id,
                product_name=item_data['product'].name,
                size=item_data['size'],
                quantity=item_data['quantity'],
                unit_price=item_data['product'].price,
                total_price=item_data['total']
            )
            db.session.add(order_item)

        if discount:
            discount.uses_count += 1

        db.session.commit()
        session['cart'] = {}
        session.pop('discount_code', None)
        session.modified = True

        flash(f'Order {order.order_number} placed successfully!', 'success')
        return redirect(url_for('account.order_detail', order_id=order.id))

    discount, discount_amount, discount_error = get_applied_discount(subtotal)
    if discount_error:
        flash(discount_error, 'danger')
    grand_total = max(subtotal + shipping - discount_amount, 0)

    addresses = current_user.addresses if current_user.is_authenticated else []
    return render_template('main/checkout.html',
                           items=items,
                           subtotal=subtotal,
                           shipping=shipping,
                           discount=discount,
                           discount_amount=discount_amount,
                           grand_total=grand_total,
                           addresses=addresses)