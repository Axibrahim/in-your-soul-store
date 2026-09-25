from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import User, Address, Order, RefundRequest, RefundImage, db
from app.password_policy import validate_password
from app.email import send_refund_request_email
from datetime import datetime, timedelta

account_bp = Blueprint('account', __name__)

# Abuse guardrails on refund requests, independent of the per-order 48h
# window. ASSUMPTION: the monthly cap wasn't given a clear number, so this
# defaults to 2/month — change this one constant if you want a different
# number.
REFUND_DAILY_LIMIT = 1
REFUND_MONTHLY_LIMIT = 2

@account_bp.route('/')
@login_required
def dashboard():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('account/dashboard.html', orders=orders)


@account_bp.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('account/orders.html', orders=orders)


@account_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()
    return render_template('account/order_detail.html', order=order)


@account_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()

        if not first_name or not last_name:
            flash('Name fields cannot be empty.', 'danger')
            return redirect(url_for('account.profile'))

        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.phone = phone
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('account.profile'))

    return render_template('account/profile.html')


@account_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_pass = request.form.get('current_password', '')
    new_pass = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    if not current_user.check_password(current_pass):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('account.profile'))

    if new_pass != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('account.profile'))

    errors = validate_password(new_pass, username=current_user.username, email=current_user.email)
    if errors:
        flash('Password too weak: ' + ' '.join(errors), 'danger')
        return redirect(url_for('account.profile'))

    if current_user.check_password(new_pass):
        flash('New password must be different from your current one.', 'danger')
        return redirect(url_for('account.profile'))

    current_user.set_password(new_pass)
    db.session.commit()
    flash('Password changed successfully.', 'success')
    return redirect(url_for('account.profile'))


@account_bp.route('/addresses')
@login_required
def addresses():
    return render_template('account/addresses.html', addresses=current_user.addresses)


@account_bp.route('/addresses/add', methods=['POST'])
@login_required
def add_address():
    label = request.form.get('label', 'Home').strip()
    street = request.form.get('street', '').strip()
    building = request.form.get('building', '').strip()
    floor = request.form.get('floor', '').strip()
    apartment = request.form.get('apartment', '').strip()
    landmark = request.form.get('landmark', '').strip()
    district = request.form.get('district', '').strip()
    governorate = request.form.get('governorate', '').strip()
    is_default = request.form.get('is_default') == 'on'

    if not all([street, building, floor, district, governorate]):
        flash('Street, building, floor, district and governorate are required.', 'danger')
        return redirect(url_for('account.addresses'))

    if is_default:
        for addr in current_user.addresses:
            addr.is_default = False

    address = Address(
        user_id=current_user.id,
        label=label,
        street=street,
        building=building,
        floor=floor,
        apartment=apartment or None,
        landmark=landmark or None,
        district=district,
        governorate=governorate,
        is_default=is_default
    )
    db.session.add(address)
    db.session.commit()
    flash('Address added.', 'success')
    return redirect(url_for('account.addresses'))

@account_bp.route('/addresses/<int:addr_id>/delete', methods=['POST'])
@login_required
def delete_address(addr_id):
    addr = Address.query.filter_by(id=addr_id, user_id=current_user.id).first_or_404()
    db.session.delete(addr)
    db.session.commit()
    flash('Address removed.', 'success')
    return redirect(url_for('account.addresses'))


@account_bp.route('/addresses/<int:addr_id>/set-default', methods=['POST'])
@login_required
def set_default_address(addr_id):
    for addr in current_user.addresses:
        addr.is_default = False
    addr = Address.query.filter_by(id=addr_id, user_id=current_user.id).first_or_404()
    addr.is_default = True
    db.session.commit()
    return jsonify({'success': True})

@account_bp.route('/track-order/<order_number>')
@login_required
def track_order(order_number):
    order = Order.query.filter_by(order_number=order_number, user_id=current_user.id).first_or_404()
    return redirect(url_for('account.order_detail', order_id=order.id))


@account_bp.route('/order/<int:order_id>/refund', methods=['POST'])
@login_required
def request_refund(order_id):
    # Imported lazily to avoid a circular import (admin.py doesn't import account.py).
    from app.routes.admin import save_product_image

    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first_or_404()

    if order.status != 'delivered':
        flash('Refunds can only be requested for delivered orders.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    if not order.refund_window_open():
        flash('The 48-hour refund window for this order has closed.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    if order.active_refund_request():
        flash('You already have an active refund request for this order.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    since_daily = datetime.utcnow() - timedelta(days=1)
    since_monthly = datetime.utcnow() - timedelta(days=30)
    daily_count = RefundRequest.query.filter(
        RefundRequest.user_id == current_user.id,
        RefundRequest.created_at >= since_daily
    ).count()
    monthly_count = RefundRequest.query.filter(
        RefundRequest.user_id == current_user.id,
        RefundRequest.created_at >= since_monthly
    ).count()

    if daily_count >= REFUND_DAILY_LIMIT:
        flash('You can only submit one refund request per day. Please try again tomorrow.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    if monthly_count >= REFUND_MONTHLY_LIMIT:
        flash(f'You have reached the limit of {REFUND_MONTHLY_LIMIT} refund requests this month.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('Please tell us why you are requesting a refund.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    item_photo = request.files.get('item_photo')
    receipt_photo = request.files.get('receipt_photo')

    if not item_photo or not item_photo.filename:
        flash('Please attach a photo of the item.', 'danger')
        return redirect(url_for('account.order_detail', order_id=order_id))

    refund = RefundRequest(order_id=order.id, user_id=current_user.id, reason=reason)
    db.session.add(refund)
    db.session.flush()  # assigns refund.id so images can reference it

    for file, image_type in [(item_photo, 'item'), (receipt_photo, 'receipt')]:
        if file and file.filename:
            public_url = save_product_image(file, folder='refunds')
            if public_url:
                db.session.add(RefundImage(
                    refund_request_id=refund.id,
                    image_url=public_url,
                    image_type=image_type
                ))
            else:
                label = 'Item' if image_type == 'item' else 'Receipt'
                flash(f'{label} photo was not a valid image or upload failed and was skipped.', 'danger')

    db.session.commit()
    flash('Your refund request has been submitted. We will review it shortly.', 'success')

    if current_user.email:
        send_refund_request_email(current_user.email, order, refund, first_name=current_user.first_name)

    return redirect(url_for('account.order_detail', order_id=order_id))