"""
PWA endpoints.

Why these live in a blueprint instead of /static:
  * /sw.js must be served from the site ROOT, otherwise the service worker can only control /static/*.
  * the manifest is generated so its icon / shortcut URLs always match url_for().
  * /apple-touch-icon.png and /favicon.ico are the paths Safari and most browsers request by default.
None of these routes touch the database or the session, and they are exempt from the rate limiter.
"""
from flask import Blueprint, current_app, jsonify, make_response, render_template, send_from_directory, url_for

from app import limiter

pwa_bp = Blueprint('pwa', __name__)

BRAND_BG = '#040804'   # --bg in main.css


def _icon(name, max_age=86400):
    return send_from_directory(current_app.static_folder, f'icons/{name}', max_age=max_age)


@pwa_bp.route('/manifest.webmanifest')
@limiter.exempt
def manifest():
    def static(name):
        return url_for('static', filename=name)

    data = {
        'id': '/',
        'name': 'IN YOUR SOUL',
        'short_name': 'IN YOUR SOUL',
        'description': 'Egyptian rave & techno streetwear. Oversized drops built for the underground.',
        'start_url': '/?source=pwa',
        'scope': '/',
        'display': 'standalone',
        'background_color': BRAND_BG,
        'theme_color': BRAND_BG,
        'lang': 'en',
        'dir': 'ltr',
        'categories': ['shopping', 'fashion'],
        'icons': [
            {'src': static('icons/icon-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('icons/icon-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('icons/icon-maskable-192.png'), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'maskable'},
            {'src': static('icons/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
        # Long-press menu on the Android home-screen icon.
        'shortcuts': [
            {'name': 'Shop', 'short_name': 'Shop', 'url': url_for('main.shop'),
             'icons': [{'src': static('icons/shortcut-96.png'), 'sizes': '96x96', 'type': 'image/png'}]},
            {'name': 'Cart', 'short_name': 'Cart', 'url': url_for('cart.view_cart'),
             'icons': [{'src': static('icons/shortcut-96.png'), 'sizes': '96x96', 'type': 'image/png'}]},
            {'name': 'My account', 'short_name': 'Account', 'url': url_for('account.dashboard'),
             'icons': [{'src': static('icons/shortcut-96.png'), 'sizes': '96x96', 'type': 'image/png'}]},
        ],
    }
    resp = make_response(jsonify(data))
    resp.mimetype = 'application/manifest+json'
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


@pwa_bp.route('/sw.js')
@limiter.exempt
def service_worker():
    resp = send_from_directory(current_app.static_folder, 'js/sw.js', mimetype='text/javascript', max_age=0)
    # Browsers must always re-check the worker script, or a bad version could get stuck.
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@pwa_bp.route('/offline')
@limiter.exempt
def offline():
    resp = make_response(render_template('offline.html'))
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


@pwa_bp.route('/apple-touch-icon.png')
@pwa_bp.route('/apple-touch-icon-precomposed.png')
@limiter.exempt
def apple_touch_icon():
    return _icon('apple-touch-icon.png')


@pwa_bp.route('/favicon.ico')
@limiter.exempt
def favicon():
    return _icon('favicon.ico')