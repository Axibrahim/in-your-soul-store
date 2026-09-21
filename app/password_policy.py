import re

MIN_LENGTH = 10
MAX_BYTES = 72  # bcrypt only uses the first 72 bytes

_COMMON = {
    'password', 'password1', 'password123', 'passw0rd', 'qwerty', 'qwerty123',
    'qwertyuiop', '1234567890', '12345678', '123456789', 'iloveyou', 'admin123',
    'welcome1', 'welcome123', 'letmein', 'abc12345', 'football', 'monkey123',
    'inyoursoul', 'freks', 'streetwear',
}


def validate_password(password, username='', email=''):
    """Return a list of problems. Empty list = password is acceptable."""
    errors = []

    if len(password) < MIN_LENGTH:
        errors.append(f'Use at least {MIN_LENGTH} characters.')
    if len(password.encode('utf-8')) > MAX_BYTES:
        errors.append('Password is too long (max 72 bytes).')
    if not re.search(r'[a-z]', password):
        errors.append('Add a lowercase letter.')
    if not re.search(r'[A-Z]', password):
        errors.append('Add an uppercase letter.')
    if not re.search(r'\d', password):
        errors.append('Add a number.')
    if not re.search(r'[^A-Za-z0-9]', password):
        errors.append('Add a symbol (e.g. ! @ # $ %).')

    lowered = password.lower()
    stripped = re.sub(r'[^a-z0-9]', '', lowered)
    if lowered in _COMMON or any(stripped.startswith(c) for c in _COMMON if len(c) >= 8):
        errors.append('That password is too common.')

    email_local = (email or '').split('@')[0].lower()
    for part in (username, email_local):
        part = (part or '').strip().lower()
        if len(part) >= 3 and part in lowered:
            errors.append('Password must not contain your username or email.')
            break

    return errors