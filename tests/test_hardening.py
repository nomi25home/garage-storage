"""Tests for the P2 hardening features: optimistic locking, audit trail,
sync-row idempotency, and backup retention.

These tests run against the FastAPI app with OIDC disabled (see conftest.py),
so every route is open and the audit actor resolves to "anonymous".
"""

from __future__ import annotations

import sqlite3


def _db_path(client):
    import app as app_module

    return app_module.DB_NAME


def _conn(client):
    return sqlite3.connect(_db_path(client))


def _sync_row_post(client, json):
    """Helper: POST /api/sync-row with N8N_WEBHOOK_SECRET."""
    return client.post("/api/sync-row?N8N_WEBHOOK_SECRET=test-webhook-secret", json=json)


def test_sync_row_idempotent(client):
    """sync-row with an existing item_id must NOT insert a duplicate row."""
    r = _sync_row_post(client, {"bin_id": "BIN-A", "name": "Screwdriver", "category": "tools", "quantity": 3})
    assert r.status_code == 200
    first_id = r.json()["item_id"]

    # Same sheet row, same item_id — must be skipped, not duplicated.
    r = _sync_row_post(
        client,
        {
            "bin_id": "BIN-A",
            "name": "Screwdriver",
            "category": "tools",
            "quantity": 3,
            "item_id": first_id,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["item_id"] == first_id
    assert body["skipped"] is True

    with _conn(client) as conn:
        count = conn.execute("SELECT COUNT(*) FROM items WHERE item_id = ?", (first_id,)).fetchone()[0]
    assert count == 1


def test_sync_row_create_logs_audit(client):
    """Every sync-row insert writes an audit_log row."""
    _sync_row_post(client, {"bin_id": "BIN-B", "name": "Hammer", "category": "tools", "quantity": 2})
    with _conn(client) as conn:
        rows = conn.execute("SELECT action, item_id FROM audit_log WHERE action = 'sync-row-create'").fetchall()
    assert len(rows) == 1
    assert rows[0][1] is not None


def test_update_item_optimistic_lock_conflict(client, admin_client):
    """Two edits to the same item: the second (stale version) must 409."""
    # Create an item.
    r = _sync_row_post(client, {"bin_id": "BIN-C", "name": "Wrench", "category": "tools", "quantity": 1})
    item_id = r.json()["item_id"]

    # First edit succeeds and bumps the version.
    r = admin_client.patch(
        f"/update-item/{item_id}",
        json={
            "name": "Wrench",
            "category": "tools",
            "quantity": 1,
            "tags": "",
            "version": 1,
        },
    )
    assert r.status_code == 200
    new_version = r.json()["new_version"]
    assert new_version == 2

    # Second edit uses the stale version — must be rejected.
    r = admin_client.patch(
        f"/update-item/{item_id}",
        json={
            "name": "Wrench",
            "category": "tools",
            "quantity": 1,
            "tags": "",
            "version": 1,
        },
    )
    assert r.status_code == 409
    assert "stale" in r.json()["error"].lower()


def test_update_item_requires_version(client, admin_client):
    """Omitting the version field must be rejected, not silently succeed."""
    r = _sync_row_post(client, {"bin_id": "BIN-D", "name": "Saw", "category": "tools", "quantity": 1})
    item_id = r.json()["item_id"]

    r = admin_client.patch(
        f"/update-item/{item_id}",
        json={
            "name": "Saw",
            "category": "tools",
            "quantity": 1,
            "tags": "",
        },
    )
    assert r.status_code == 400
    assert "version" in r.json()["error"].lower()


def test_delete_item_logs_audit(client, admin_client):
    r = _sync_row_post(client, {"bin_id": "BIN-E", "name": "Drill", "category": "tools", "quantity": 1})
    item_id = r.json()["item_id"]

    r = admin_client.delete(f"/delete-item/{item_id}")
    assert r.status_code == 200

    with _conn(client) as conn:
        rows = conn.execute("SELECT action, item_id FROM audit_log WHERE action = 'delete-item'").fetchall()
    assert any(row[1] == item_id for row in rows)


def test_non_admin_denied_on_mutating_route(client, admin_client):
    """A session without is_admin=True must be rejected on mutating routes."""
    import json
    from base64 import b64encode

    from fastapi.testclient import TestClient
    from itsdangerous import TimestampSigner

    import app as app_module

    signer = TimestampSigner(app_module.AUTH_SECRET_KEY)
    cookie = signer.sign(
        b64encode(
            json.dumps(
                {
                    "user": {
                        "sub": "user-1",
                        "email": "user@example.com",
                        "name": "Regular User",
                        "groups": ["users"],
                    },
                    "is_admin": False,
                    "csrf_token": "test-csrf-token",
                }
            ).encode("utf-8")
        )
    ).decode("utf-8")

    with TestClient(app_module.app) as c:
        c.cookies.set("session", cookie)
        c.headers["X-CSRF-Token"] = "test-csrf-token"
        # Mutating routes must 403 for a non-admin.
        for method, path in [
            ("patch", "/update-item/1"),
            ("delete", "/delete-item/1"),
            ("post", "/api/tag-colors"),
        ]:
            r = c.request(method, path, json={"tag": "x", "hex": "#000000"})
            assert r.status_code == 403, f"{method} {path} should 403, got {r.status_code}"
        # Read routes must still work.
        r = c.get("/api/items")
        assert r.status_code == 200


def test_backup_retention_prunes(client, tmp_path):
    """More than 10 backups must be pruned to the retention limit."""
    import app as app_module

    # backup_retention() resolves /data/backups via the module-level Path.
    # Patch it so the absolute path lands inside tmp_path instead of /data.
    monkeypatch_target = app_module.Path
    app_module.Path = lambda p: tmp_path / str(p).lstrip("/")
    try:
        backups = tmp_path / "data" / "backups"
        backups.mkdir(parents=True)
        for i in range(15):
            (backups / f"old-{i}.zip").write_bytes(b"zip")
        r = client.get("/api/backup/retention")
        assert r.status_code == 200
        body = r.json()
        assert body["retention_limit"] == 10
        assert len(body["kept"]) == 10
        assert len(body["pruned"]) == 5
    finally:
        app_module.Path = monkeypatch_target
