from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.models import User, Address, Order, db
from app.password_policy import validate_password

account_bp = Blueprint('account', __name__)


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