"""Hub SSO helpers for the Pure Way Profile tool."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

HUB_URL = os.environ.get('HUB_URL', 'https://hub.purepropsolutions.com').rstrip('/')
HUB_PUBLIC_URL = os.environ.get('HUB_PUBLIC_URL', HUB_URL).rstrip('/')
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', '')


def configure_session(app):
    _debug = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    app.config.update(
        SESSION_COOKIE_SECURE=not _debug,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )


def hub_login_url(next_url=None):
    if next_url:
        return f'{HUB_PUBLIC_URL}/login?next={urllib.parse.quote(next_url, safe="")}'
    return f'{HUB_PUBLIC_URL}/login'


def exchange_sso_code(code):
    if not code or not INTERNAL_API_KEY:
        return None
    try:
        payload = json.dumps({'code': code}).encode('utf-8')
        req = urllib.request.Request(
            HUB_URL + '/exchange-code',
            data=payload,
            headers={'Content-Type': 'application/json', 'X-API-Key': INTERNAL_API_KEY},
            method='POST',
        )
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('valid'):
            return data
    except Exception as e:
        print(f'SSO code exchange error: {e}')
    return None


def logout_redirect_url(hub_login='/login'):
    final = f'{HUB_PUBLIC_URL}{hub_login}'
    return final