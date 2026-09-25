import os
import resend
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer


def _serializer():
    secret = current_app.config['SECRET_KEY']
    if not secret:
        raise RuntimeError("SECRET_KEY is not configured.")
    return URLSafeTimedSerializer(secret)


def generate_verify_token(email: str) -> str:
    return _serializer().dumps(email, salt='email-verify')


def confirm_verify_token(token: str):
    """Returns the email if the token is valid and not expired, else None."""
    try:
        max_age = current_app.config.get('EMAIL_VERIFY_MAX_AGE_SECONDS', 3600)
        return _serializer().loads(
            token,
            salt='email-verify',
            max_age=max_age,
        )
    except Exception:
        # AUDIT FIX (H1): only log that a token was invalid/expired, never
        # the exception's repr - itsdangerous exceptions can include the
        # raw payload/signature being checked.
        current_app.logger.info("Email verification token rejected (invalid or expired)")
        return None


def _resend_send_template(
    to_email: str,
    template_id: str,
    variables: dict
) -> bool:

    resend.api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_FROM_EMAIL')

    if not resend.api_key or not from_email:
        current_app.logger.error(
            "Resend not configured: RESEND_API_KEY / RESEND_FROM_EMAIL missing"
        )
        return False

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "template": {
                "id": template_id,
                "variables": variables,
            },
        })
        return True

    except Exception:
        current_app.logger.exception("Failed to send template email via Resend")
        return False


def send_verification_email(to_email: str, token: str, first_name: str = "") -> bool:
    base_url = os.environ.get('BASE_URL', 'https://inyoursoul.store').rstrip('/')

    try:
        path = url_for('auth.verify_email', token=token)
    except Exception:
        path = f"/verify-email/{token}"

    full_link = f"{base_url}{path}"

    # AUDIT FIX (H1): this used to print() the full verification link -
    # including the raw signed token - to stderr, which Railway keeps as
    # plain-text logs anyone with log access could read and use to verify
    # (or take over, pre-verification) any account. Never log the link/token.
    current_app.logger.info("Sending verification email to %s", to_email)

    variables = {
        "verification_url": full_link,
        "first_name": first_name or "Friend"
    }

    return _resend_send_template(
        to_email=to_email,
        template_id='5801c34f-63fb-44fe-9fd5-819d352f24d7',
        variables=variables
    )


def generate_reset_token(email: str) -> str:
    return _serializer().dumps(email, salt='password-reset')


def confirm_reset_token(token: str):
    """Returns the email if valid and not expired, else None."""
    try:
        max_age = current_app.config.get('PASSWORD_RESET_MAX_AGE_SECONDS', 1800)
        return _serializer().loads(
            token,
            salt='password-reset',
            max_age=max_age,
        )
    except Exception:
        current_app.logger.info("Password reset token rejected (invalid or expired)")
        return None


def send_reset_email(to_email: str, token: str) -> bool:
    base_url = os.environ.get('BASE_URL', 'https://inyoursoul.store').rstrip('/')
    try:
        path = url_for('auth.reset_password', token=token)
    except Exception:
        path = f"/reset-password/{token}"

    link = f"{base_url}{path}"

    # AUDIT FIX (H1): same reasoning as send_verification_email() above -
    # this link contains the raw password-reset token. Never log it.
    current_app.logger.info("Sending password reset email to %s", to_email)

    body = (
        f"We received a request to reset your IN YOUR SOUL password.\n\n"
        f"Click the link below to set a new password. It expires in 30 minutes.\n\n{link}\n\n"
        f"If you didn't request this, you can safely ignore this email — "
        f"your password will not be changed."
    )

    resend.api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_FROM_EMAIL')

    if not resend.api_key or not from_email:
        current_app.logger.error(
            "Resend not configured: RESEND_API_KEY / RESEND_FROM_EMAIL missing"
        )
        return False

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": "Reset your IN YOUR SOUL password",
            "text": body,
        })
        return True

    except Exception:
        current_app.logger.exception("Failed to send password reset email")
        return False


def send_order_status_email(
    to_email: str,
    order_id: str,
    order_status: str = "Processing",
    estimated_delivery: str = "3-5 Business Days",
    first_name: str = ""
) -> bool:
    base_url = os.environ.get('BASE_URL', 'https://inyoursoul.store').rstrip('/')

    try:
        path = url_for('account.track_order', order_number=order_id)
    except Exception:
        path = f"/track-order/{order_id}"

    resend.api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_ORDERS_FROM_EMAIL')

    if not resend.api_key or not from_email:
        current_app.logger.error(
            "Resend not configured: RESEND_API_KEY / RESEND_ORDERS_FROM_EMAIL missing"
        )
        return False

    variables = {
        "order_tracking_url": f"{base_url}{path}",  # Output: https://inyoursoul.store/track-order/123
        "order_id": order_id,                       # Send as number or string matching template type
        "order_status": order_status,
        "estimated_delivery": estimated_delivery,
        "first_name": first_name or "Friend"
    }
    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"Update on your order #{order_id}",
            "template": {
                "id": "39d43d95-5733-456e-9c11-a81dd81e5eaa",
                "variables": variables,
            },
        })
        current_app.logger.info("Order status email sent for order %s (%s)", order_id, order_status)
        return True

    except Exception:
        current_app.logger.exception("Failed to send order status email for order %s", order_id)
        return False

def send_refund_request_email(to_email: str, order, refund, first_name: str = "") -> bool:
    """Confirms to the customer that their refund request was received and is pending review."""
    base_url = os.environ.get('BASE_URL', 'https://inyoursoul.store').rstrip('/')

    try:
        path = url_for('account.order_detail', order_id=order.id)
    except Exception:
        path = f"/account/order/{order.id}"

    link = f"{base_url}{path}"

    current_app.logger.info(
        "Sending refund request confirmation for order %s to %s", order.order_number, to_email
    )

    body = (
        f"Hi {first_name or 'there'},\n\n"
        f"We've received your refund request for order #{order.order_number}.\n\n"
        f"Our team will review it and get back to you within 2-3 business days.\n\n"
        f"You can check the status of your request here:\n{link}\n\n"
        f"Thanks for your patience."
    )

    resend.api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_ORDERS_FROM_EMAIL') or os.environ.get('RESEND_FROM_EMAIL')

    if not resend.api_key or not from_email:
        current_app.logger.error(
            "Resend not configured: RESEND_API_KEY / RESEND_ORDERS_FROM_EMAIL missing"
        )
        return False

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"Refund request received — order #{order.order_number}",
            "text": body,
        })
        return True

    except Exception:
        current_app.logger.exception(
            "Failed to send refund request confirmation for order %s", order.order_number
        )
        return False


def send_refund_status_email(to_email: str, order, refund, first_name: str = "") -> bool:
    """Notifies the customer that their refund request was approved or rejected."""
    base_url = os.environ.get('BASE_URL', 'https://inyoursoul.store').rstrip('/')

    try:
        path = url_for('account.order_detail', order_id=order.id)
    except Exception:
        path = f"/account/order/{order.id}"

    link = f"{base_url}{path}"
    approved = refund.status == 'approved'

    current_app.logger.info(
        "Sending refund status email (%s) for order %s to %s", refund.status, order.order_number, to_email
    )

    if approved:
        body = (
            f"Hi {first_name or 'there'},\n\n"
            f"Good news — your refund request for order #{order.order_number} has been approved.\n\n"
            f"We'll process your refund shortly. If you paid online, it can take a few business "
            f"days to appear on your statement.\n\n"
            f"View your order: {link}"
        )
    else:
        body = (
            f"Hi {first_name or 'there'},\n\n"
            f"Your refund request for order #{order.order_number} was not approved.\n\n"
            f"If you think this is a mistake or want more details, reply to this email and we'll help.\n\n"
            f"View your order: {link}"
        )

    resend.api_key = os.environ.get('RESEND_API_KEY')
    from_email = os.environ.get('RESEND_ORDERS_FROM_EMAIL') or os.environ.get('RESEND_FROM_EMAIL')

    if not resend.api_key or not from_email:
        current_app.logger.error(
            "Resend not configured: RESEND_API_KEY / RESEND_ORDERS_FROM_EMAIL missing"
        )
        return False

    try:
        resend.Emails.send({
            "from": from_email,
            "to": [to_email],
            "subject": f"Refund {'approved' if approved else 'update'} — order #{order.order_number}",
            "text": body,
        })
        return True

    except Exception:
        current_app.logger.exception(
            "Failed to send refund status email for order %s", order.order_number
        )
        return False