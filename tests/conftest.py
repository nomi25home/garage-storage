"""Pytest fixtures for kapaat.

Redirects DB_PATH, PHOTOS_DIR and the backup-retention directory to a
temporary directory so the test suite runs without /data being writable.
"""
from __future__ import annotations

import json
import os
import tempfile
from base64 import b64encode

# import pytest  # unused in fixtures

# Must happen BEFORE app is imported: app.py reads these env vars at module load.
_TMP = tempfile.mkdtemp(prefix="kapaat-test-")
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "garage_inventory.db"))
os.environ.setdefault("PHOTOS_DIR", os.path.join(_TMP, "photos"))
# Locale files ship in the repo; point at them rather than the temp dir so
# app.py's module-load _load_locale() finds en.json.
os.environ.setdefault("LOCALE_DIR", os.path.join(os.path.dirname(__file__), "..", "locales"))
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.pop("AUTHENTIK_CLIENT_ID", None)  # disable OIDC so routes are open
# N8N webhook secret so tests can authenticate to /api/sync-row.
os.environ.setdefault("N8N_WEBHOOK_SECRET", "test-webhook-secret")


@pytest.fixture(autouse=True)
def _reset_db():
    """Each test starts from a clean database.

    app.py is imported once and DB_PATH is fixed at import time, so without
    this every test would see the previous test's rows (audit_log in
    particular accumulates across the whole suite).
    """
    import app as app_module

    db_path = app_module.DB_NAME

    if os.path.exists(db_path):
        os.unlink(db_path)
    app_module.init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import app as app_module

    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture
def admin_client():
    """Test client with an authenticated admin session injected.

    The admin check in v1.2.2 looks at request.session["is_admin"].
    FastAPI's TestClient with SessionMiddleware doesn't expose
    session_transaction (that's Flask/Django), so we build a signed
    session cookie using the same serializer Starlette's SessionMiddleware uses.
    """
    from fastapi.testclient import TestClient
    from itsdangerous import TimestampSigner

    import app as app_module

    with TestClient(app_module.app) as c:
        # Starlette's SessionMiddleware signs with itsdangerous.TimestampSigner
        # (no salt) — match that exactly so the middleware unsigns our cookie.
        signer = TimestampSigner(app_module.AUTH_SECRET_KEY)
        session_data = {
            "user": {
                "sub": "test-admin",
                "email": "admin@example.com",
                "name": "Test Admin",
                "groups": ["admins"],
            },
            "is_admin": True,
        }
        cookie_val = signer.sign(
            b64encode(json.dumps(session_data).encode("utf-8"))
        ).decode("utf-8")
        c.cookies.set("session", cookie_val)
        yield c


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Redirect app.Path so backup-retention writes into tmp_path."""
    import app as app_module

    monkeypatch.setattr(app_module, "Path", lambda p: tmp_path / p)
    return tmp_path
