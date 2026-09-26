# =============================================================================
# FREKS — app/auth_guard.py
# Token-based authentication protection layer
#
# HOW IT WORKS:
# On every successful login, we generate a unique secure token and store it
# in the database tied to that user session. Every protected request checks
# that the token in the user's session cookie matches the one in the DB.
# If someone steals a session cookie, you can invalidate it instantly by
# revoking the token — without changing the password.
# =============================================================================

import secrets
import hashlib
from datetime import datetime, timedelta
from functools import wraps

from flask import session, redirect, url_for, flash, request, g
from flask_login import current_user

from app.models import User
from app.models import db


# ── HOW TOKENS WORK ───────────────────────────────────────────────────────────
#
#  1. User logs in successfully
#  2. We call issue_session_token(user) → generates a random 64-char hex token
#  3. We store a SHA-256 HASH of the token in the DB (user.session_token)
#     → We never store the raw token in the DB, only its hash
#     → This way even if someone reads your DB they can't use the token
#  4. The RAW token goes into Flask's encrypted session cookie on the browser
#  5. On every request to a protected route, validate_session_token() runs:
#     → It reads the raw token from the cookie
#     → Hashes it and compares to the hash stored in DB
#     → If they match → request is allowed
#     → If they don't match → session is killed, user is logged out
#  6. On logout, revoke_session_token(user) sets user.session_token = None
#     → Now the cookie is useless even if someone kept a copy of it
#
# ── WHAT THIS PROTECTS AGAINST ────────────────────────────────────────────────
#
#  ✓ Session fixation attacks (each login gets a fresh token)
#  ✓ Stolen session cookies (revoke token → cookie becomes useless instantly)
#  ✓ Concurrent session abuse (new login revokes all old sessions)
#  ✓ "Remember me" token theft (same revocation applies)
#  ✓ Admin account hijacking (extra token_required_admin layer)
# =============================================================================


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash a raw token. Only the hash is stored in the DB."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def issue_session_token(user: User) -> None:
    """
    Call this right after login_user(user).
    Generates a fresh token, stores its hash in DB, puts raw token in session.
    """
    raw_token = secrets.token_hex(32)          # 64 random hex characters
    user.session_token = _hash_token(raw_token)
    user.session_issued_at = datetime.utcnow()
    db.session.commit()
    session['_auth_token'] = raw_token         # goes into the browser cookie


def revoke_session_token(user: User) -> None:
    """
    Call this on logout or when you want to force-kick a user.
    Wipes the token from DB → any existing cookie becomes invalid.
    """
    user.session_token = None
    user.session_issued_at = None
    db.session.commit()
    session.pop('_auth_token', None)


def validate_session_token() -> bool:
    """
    Returns True if the session cookie token matches what's in the DB.
    Returns False if token is missing, expired, or doesn't match.
    """
    if not current_user.is_authenticated:
        return True  # unauthenticated routes don't need token check

    raw_token = session.get('_auth_token')
    if not raw_token:
        return False  # no token in cookie at all

    if not current_user.session_token:
        return False  # no token stored in DB (was revoked)

    # Compare hashed version of cookie token against DB hash
    if _hash_token(raw_token) != current_user.session_token:
        return False  # mismatch → possible stolen cookie

    # Sliding expiry: 7 days of inactivity logs you out, but every valid
    # request rolls the window forward. An active "remember me" user never
    # hits a hard wall; someone who walks away for a week does.
    if current_user.session_issued_at:
        age = datetime.utcnow() - current_user.session_issued_at
        if age > timedelta(days=7):
            return False  # token too old

    current_user.session_issued_at = datetime.utcnow()
    db.session.commit()

    return True


# ── DECORATORS ────────────────────────────────────────────────────────────────

def token_required(f):
    """
    Use this decorator on any route that needs token validation.

    Usage:
        @account_bp.route('/dashboard')
        @login_required          ← always put login_required FIRST
        @token_required          ← then token_required
        def dashboard():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and not validate_session_token():
            # Token invalid → kill the session, redirect to login
            from flask_login import logout_user
            logout_user()
            session.clear()
            flash('Your session has expired or was invalidated. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def token_required_admin(f):
    """
    Stricter version for admin routes.
    Checks both token validity AND admin flag.

    Usage:
        @admin_bp.route('/dashboard')
        @login_required
        @token_required_admin
        def dashboard():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in.', 'danger')
            return redirect(url_for('auth.login'))

        if not validate_session_token():
            from flask_login import logout_user
            logout_user()
            session.clear()
            flash('Admin session expired. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))

        if not current_user.is_admin:
            flash('Access denied.', 'danger')
            return redirect(url_for('main.index'))

        return f(*args, **kwargs)
    return decorated


def register_token_hooks(app):
    """
    Call this in create_app() to automatically validate tokens
    on every request without decorating every single route manually.

    This is the recommended approach — one place, covers everything.
    """
    @app.before_request
    def check_token_on_every_request():
        # Skip static files, login, register, logout — they don't need token
        open_endpoints = {'auth.login', 'auth.register', 'auth.logout', 'static'}
        if request.endpoint in open_endpoints:
            return

        if current_user.is_authenticated and not validate_session_token():
            from flask_login import logout_user
            logout_user()
            session.clear()
            flash('Your session expired. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))