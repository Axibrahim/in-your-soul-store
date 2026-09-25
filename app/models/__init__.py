from app import db, login_manager, bcrypt
from flask_login import UserMixin
from datetime import datetime, timedelta
import json


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), unique=True, nullable=True)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    session_token = db.Column(db.String(64), nullable=True)
    session_issued_at = db.Column(db.DateTime, nullable=True)

    addresses = db.relationship('Address', backref='user', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    label = db.Column(db.String(50), default='Home')
    street = db.Column(db.String(200), nullable=False)
    building = db.Column(db.String(50), nullable=False)
    floor = db.Column(db.String(20), nullable=False)
    apartment = db.Column(db.String(20), nullable=True)
    landmark = db.Column(db.String(150), nullable=True)
    district = db.Column(db.String(100), nullable=False)
    governorate = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Address {self.label} - {self.governorate}>'

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    image_url = db.Column(db.String(300))
    image_url_2 = db.Column(db.String(300))
    image_url_3 = db.Column(db.String(300))
    image_url_4 = db.Column(db.String(300))
    is_featured = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan')
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

    def get_total_stock(self):
        return sum(v.stock for v in self.variants)

    def __repr__(self):
        return f'<Product {self.name}>'


class ProductVariant(db.Model):
    __tablename__ = 'product_variants'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    size = db.Column(db.String(10), nullable=False)  # XS, S, M, L, XL, XXL
    stock = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Variant {self.size}: {self.stock}>'


class DiscountCode(db.Model):
    __tablename__ = 'discount_codes'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    discount_type = db.Column(db.String(10), nullable=False, default='percent')  # 'percent' or 'fixed'
    value = db.Column(db.Float, nullable=False)  # percent (0-100) or fixed EGP amount
    min_subtotal = db.Column(db.Float, default=0)
    max_uses = db.Column(db.Integer, nullable=True)  # None = unlimited
    uses_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self, subtotal):
        if not self.is_active:
            return False, "This code is no longer active."
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False, "This code has expired."
        if self.max_uses is not None and self.uses_count >= self.max_uses:
            return False, "This code has reached its usage limit."
        if subtotal < self.min_subtotal:
            return False, f"Minimum order of {self.min_subtotal:.0f} EGP required for this code."
        return True, None

    def calculate_discount(self, subtotal):
        if self.discount_type == 'percent':
            return round(subtotal * (self.value / 100), 2)
        return min(self.value, subtotal)  # fixed amount, never exceeds subtotal

    def __repr__(self):
        return f'<DiscountCode {self.code}>'


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, confirmed, shipped, delivered, cancelled
    payment_method = db.Column(db.String(50), nullable=False)  # cod, vodafone_cash, instapay
    payment_deadline = db.Column(db.DateTime, nullable=True)
    payment_status = db.Column(db.String(50), default='unpaid')
    subtotal = db.Column(db.Float, default=0)
    shipping_cost = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    discount_code = db.Column(db.String(30), nullable=True)
    discount_amount = db.Column(db.Float, default=0)
    shipping_address = db.Column(db.Text)  # JSON string of address
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)  # set the moment status first becomes 'delivered'; drives the 48h refund window
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    refund_requests = db.relationship('RefundRequest', backref='order', lazy=True, cascade='all, delete-orphan')

    REFUND_WINDOW_HOURS = 48

    def refund_deadline(self):
        if not self.delivered_at:
            return None
        return self.delivered_at + timedelta(hours=self.REFUND_WINDOW_HOURS)

    def refund_window_open(self):
        deadline = self.refund_deadline()
        return bool(deadline and datetime.utcnow() <= deadline)

    def active_refund_request(self):
        """Most recent refund request that isn't rejected, if any - used to block duplicate submissions."""
        for r in sorted(self.refund_requests, key=lambda r: r.created_at, reverse=True):
            if r.status != 'rejected':
                return r
        return None
    
    def get_shipping_address(self):
        try:
            return json.loads(self.shipping_address) if self.shipping_address else {}
        except:
            return {}

    def set_shipping_address(self, addr_dict):
        self.shipping_address = json.dumps(addr_dict)

    @staticmethod
    def generate_order_number():
        import random, string
        return 'FRK-' + ''.join(random.choices(string.digits, k=8))

    def __repr__(self):
        return f'<Order {self.order_number}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id'))
    product_name = db.Column(db.String(200))
    size = db.Column(db.String(10))
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float)
    total_price = db.Column(db.Float)

    variant = db.relationship('ProductVariant', backref='order_items')

    def __repr__(self):
        return f'<OrderItem {self.product_name} x{self.quantity}>'


class RefundRequest(db.Model):
    __tablename__ = 'refund_requests'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('refund_requests', lazy=True))
    images = db.relationship('RefundImage', backref='refund_request', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RefundRequest order={self.order_id} status={self.status}>'


class RefundImage(db.Model):
    __tablename__ = 'refund_images'
    id = db.Column(db.Integer, primary_key=True)
    refund_request_id = db.Column(db.Integer, db.ForeignKey('refund_requests.id'), nullable=False)
    image_url = db.Column(db.String(300), nullable=False)
    image_type = db.Column(db.String(20), nullable=False)  # 'item' (order/product proof) or 'receipt' (payment proof)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<RefundImage {self.image_type} for refund={self.refund_request_id}>'