from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import jsonify, render_template
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from config import config
import os

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["1000 per hour"])
# SimpleCache = in-process memory, no Redis/new infra needed. Note: with multiple
# Gunicorn worker processes, each worker keeps its own separate cache copy (not
# shared), so cache hit rate is somewhat lower than with a shared backend like
# Redis — but it still massively cuts DB round-trips per worker under load,
# which is exactly what's needed given the 5-connection Supabase pooler cap.
cache = Cache(config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 30})

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    if config_name == 'production':
        if not app.config['SECRET_KEY']:
            raise RuntimeError("SECRET_KEY env var must be set in production.")
        if not os.environ.get('DATABASE_URL'):
            raise RuntimeError("DATABASE_URL env var must be set in production.")

    # Rate manager
    limiter.init_app(app)
    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return render_template('errors/429.html'), 429

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.static_folder, 'videos'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)

    

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: https://hjnktfczdhcjoflmozew.supabase.co; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self'; "
            "media-src 'self'; "
            "frame-ancestors 'none'"
        )
        if not app.debug:
            response.headers['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )
        return response



    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.account import account_bp
    from app.routes.admin import admin_bp
    from app.routes.cart import cart_bp
    from app.routes.pwa import pwa_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(account_bp, url_prefix='/account')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(cart_bp, url_prefix='/cart')
    app.register_blueprint(pwa_bp)

    from app.auth_guard import register_token_hooks
    register_token_hooks(app)

    

    return app