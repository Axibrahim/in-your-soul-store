from urllib.parse import urlparse
from app.password_policy import validate_password
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import limiter
from app.auth_guard import issue_session_token, revoke_session_token
from app.email import (
    confirm_reset_token,
    confirm_verify_token,
    generate_reset_token,
    generate_verify_token,
    send_reset_email,
    send_verification_email,
)
from app.models import User, db


def _safe_next_url(target):
    """Only allow redirecting to a relative, in-app path (blocks open-redirect)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    if not target.startswith('/') or target.startswith('//'):
        return None
    return target


auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
# AUDIT FIX (H3): limit was on the whole view (GET+POST), so loading the
# login page counted the same as a login attempt - a legitimate user who
# reloaded the page a couple of times while typing could get 429'd before
# ever submitting. methods=['POST'] restricts the count to actual attempts.
@limiter.limit('5 per minute', methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user and user.check_password(password):
            if not user.email_verified:
                session['pending_verify_user_id'] = user.id
                flash('Please verify your email before logging in.', 'danger')
                return redirect(url_for('auth.check_email'))
            
            issue_session_token(user)
            db.session.commit()
            login_user(user, remember=bool(remember))
            
            next_page = _safe_next_url(request.args.get('next'))
            flash(f'Welcome back, {user.first_name}', 'success')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first() if email else None

        if user and user.email_verified:
            token = generate_reset_token(user.email)
            send_reset_email(user.email, token)

        flash(
            'If that verified email belongs to an account, a reset link has been sent.',
            'info',
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    email = confirm_reset_token(token)
    if not email:
        flash('That password reset link is invalid or expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user or not user.email_verified:
        flash('That password reset link is invalid or expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        errors = validate_password(password, username=user.username, email=user.email)
        if errors:
            flash('Password too weak: ' + ' '.join(errors), 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        user.set_password(password)
        user.session_token = None
        user.session_issued_at = None
        db.session.commit()
        flash('Your password has been reset. You can log in now.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('3 per hour')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()

        if not all([username, email, phone, password, first_name, last_name]):
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')

        if '@' not in email or '.' not in email.split('@')[-1]:
            flash('Please enter a valid email address.', 'danger')
            return render_template('auth/register.html')

        if not phone.replace('+', '').replace(' ', '').isdigit() or len(phone) < 8:
            flash('Please enter a valid phone number.', 'danger')
            return render_template('auth/register.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')

        errors = validate_password(password, username=username, email=email)
        if errors:
            flash('Password too weak: ' + ' '.join(errors), 'danger')
            return render_template('auth/register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        if User.query.filter(db.func.lower(User.username) == username).first():
            flash('Username already taken.', 'danger')
            return render_template('auth/register.html')

        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email_verified=False,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        token = generate_verify_token(email)
        send_verification_email(email, token, first_name=first_name)

        session['pending_verify_user_id'] = user.id
        flash('Check your email for a verification link.', 'info')
        return redirect(url_for('auth.check_email'))

    return render_template('auth/register.html')


@auth_bp.route('/check-email')
def check_email():
    if not session.get('pending_verify_user_id'):
        return redirect(url_for('auth.register'))
    return render_template('auth/check_email.html')


@auth_bp.route('/verify-email/<token>')
def verify_email(token):
    # AUDIT FIX (H1): these used to print() the decoded email and, via
    # confirm_verify_token()'s own debug print in email.py, the raw token
    # itself to stderr - which Railway captures as plain-text logs. Anyone
    # with log access could read a live verification token straight out of
    # the logs. Replaced with app.logger calls that never include the token,
    # and only log the user id (not the email address) once we have one.
    email = confirm_verify_token(token)
    if not email:
        current_app.logger.info("Email verification failed: invalid or expired token")
        flash('That verification link is invalid or expired.', 'danger')
        return redirect(url_for('auth.resend_verification'))

    user = User.query.filter_by(email=email).first()
    if not user:
        current_app.logger.warning("Email verification token decoded but no matching account exists")
        flash('Account not found.', 'danger')
        return redirect(url_for('auth.register'))

    session.pop('pending_verify_user_id', None)

    try:
        user.email_verified = True
        issue_session_token(user)
        db.session.commit()
        current_app.logger.info("User %s verified their email", user.id)
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to mark user %s as email-verified", user.id)
        flash('Database update error. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    login_user(user, remember=True)
    flash('Email verified! You are now logged in.', 'success')
    return redirect(url_for('main.index'))




@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def resend_verification():
    if request.method == 'POST':
        user_id = session.get('pending_verify_user_id')
        user = User.query.get(user_id) if user_id else None
        if user and not user.email_verified:
            token = generate_verify_token(user.email)
            send_verification_email(user.email, token, first_name=user.first_name)
            flash('Verification email resent.', 'info')
        else:
            flash('Nothing to resend.', 'info')
        return redirect(url_for('auth.check_email'))
    return render_template('auth/resend_verification.html')


@auth_bp.route('/logout')
@login_required
def logout():
    revoke_session_token(current_user)
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))