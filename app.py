import io
import json
import os
import re
import sqlite3
import time
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from authlib.integrations.starlette_client import OAuth
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Per-IP auth attempt tracking for backoff algorithm (v1.2.2)
_attempts: dict[str, dict] = {}  # ip → {"count": int, "first_ts": float, "last_ts": float}

app = FastAPI(title=os.environ.get("APP_TITLE", "Kapaat"))

AUTH_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "change-me-in-production")
app.add_middleware(SessionMiddleware, secret_key=AUTH_SECRET_KEY)

AUTHENTIK_CLIENT_ID = os.environ.get("AUTHENTIK_CLIENT_ID", "")
AUTHENTIK_CLIENT_SECRET = os.environ.get("AUTHENTIK_CLIENT_SECRET", "")
AUTHENTIK_ISSUER_URL = os.environ.get("AUTHENTIK_ISSUER_URL", "").rstrip("/")

oauth = OAuth()
if AUTHENTIK_CLIENT_ID:
    oauth.register(
        name="authentik",
        client_id=AUTHENTIK_CLIENT_ID,
        client_secret=AUTHENTIK_CLIENT_SECRET,
        server_metadata_url=f"{AUTHENTIK_ISSUER_URL}/.well-known/openid-configuration",
        # Request scopes needed for user identity and group-based authorization.
        client_kwargs={"scope": "openid profile email groups"},
    )

templates = Jinja2Templates(directory="templates")

if Path("static").exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

_LOCALE_DIR = Path(os.environ.get("LOCALE_DIR", "locales"))
_ACTIVE_LOCALE = os.environ.get("LOCALE", "en")


def _load_locale(code: str) -> dict:
    path = _LOCALE_DIR / f"{code}.json"
    if not path.exists():
        path = _LOCALE_DIR / "en.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_LOCALE = _load_locale(_ACTIVE_LOCALE)
DB_NAME = os.environ.get("DB_PATH", "/data/garage_inventory.db")
PHOTOS_DIR = Path(os.environ.get("PHOTOS_DIR", "/data/photos"))

# Optional AES-256 encryption via SQLCipher. Set DB_ENCRYPTION_KEY in .env to enable.
# WARNING: if you lose the key, you lose access to your data.
DB_ENCRYPTION_KEY = re.sub(r"['\";]", "", os.environ.get("DB_ENCRYPTION_KEY", "").strip())
# Multi-user access control env vars (v1.2.2)
ALLOWED_EMAILS = os.environ.get("ALLOWED_EMAILS", "").strip()
BLOCKED_EMAILS = os.environ.get("BLOCKED_EMAILS", "").strip()
ADMIN_GROUP = os.environ.get("ADMIN_GROUP", "admins")
N8N_WEBHOOK_SECRET = os.environ.get("N8N_WEBHOOK_SECRET", "").strip()
SERVICE_USER_SUB = os.environ.get("SERVICE_USER_SUB", "service-user")

if DB_ENCRYPTION_KEY:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        print(
            "WARNING: DB_ENCRYPTION_KEY is set but pysqlcipher3 is not installed. Falling back to unencrypted SQLite."
        )
        DB_ENCRYPTION_KEY = ""

# Public URL used to build QR code deep-links (must be reachable from phones on the same network).
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8096")

# Optional: n8n webhook for Google Sheets sync. Leave blank to disable.
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")


def _require_auth(request: Request):
    """Return the session user dict, or raise/redirect if OIDC is enabled and no session."""
    if not AUTHENTIK_CLIENT_ID:
        return None
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _require_auth_html(request: Request):
    """Like _require_auth but redirects to /login for browser (HTML) routes."""
    if not AUTHENTIK_CLIENT_ID:
        return None
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return user


def get_actor(request: Request | None = None) -> str:
    """Return the current user's identity for audit logging.
    Falls back to 'anonymous' when no session or OIDC disabled."""
    if request is None:
        return "anonymous"
    user = request.session.get("user")
    if not user:
        return "anonymous"
    return user.get("name") or user.get("email") or user.get("sub") or "anonymous"


def require_admin(request: Request) -> None:
    """Deny non-admins from mutating routes.

    The email gate already ran at login, so this only checks the admin
    flag. Authentik group membership is revocable — change the group
    membership and the next login takes effect immediately.

    If ADMIN_GROUP is unconfigured (empty), the check is skipped so the
    app remains usable in single-user mode.
    """
    if not ADMIN_GROUP:
        return
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=403, detail="admin required")


def log_audit(
    conn: sqlite3.Connection, request: Request | None, action: str, item_id: int | None = None, details: str = ""
) -> None:
    """Write an audit_log row. Best-effort — never raises to the caller.

    The row is committed here so it can't be silently dropped when the
    connection closes. Callers must invoke log_audit AFTER their own
    conn.commit(), never inside a still-open transaction: a later rollback
    would take the audit row back with it and the mutation would read as
    unaudited.
    """
    try:
        conn.execute(
            """INSERT INTO audit_log (actor, action, item_id, details)
               VALUES (?, ?, ?, ?)""",
            (get_actor(request), action, item_id, details),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # audit_log table may not exist yet (pre-migration DB)


def get_db():
    conn = sqlite3.connect(DB_NAME)
    if DB_ENCRYPTION_KEY:
        conn.execute(f"PRAGMA key = '{DB_ENCRYPTION_KEY}';")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_v1(conn: sqlite3.Connection):
    """Migration 1: rebuild items table with ON DELETE CASCADE.
    SQLite cannot ALTER FK constraints, so rename → recreate → copy → drop."""
    # Backfill columns that predate the registry (item_photo, tags, etc.).
    for stmt in [
        "ALTER TABLE items ADD COLUMN item_photo TEXT",
        "ALTER TABLE bins ADD COLUMN bin_photo TEXT",
        "ALTER TABLE items ADD COLUMN tags TEXT DEFAULT ''",
        "ALTER TABLE bins ADD COLUMN room TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass
    conn.executescript("""
        PRAGMA foreign_keys = OFF;
        BEGIN;
        ALTER TABLE items RENAME TO _items_old;
        CREATE TABLE items (
            item_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id    TEXT,
            name      TEXT NOT NULL,
            category  TEXT,
            quantity  INTEGER DEFAULT 1,
            item_photo TEXT,
            tags      TEXT DEFAULT '',
            FOREIGN KEY (bin_id) REFERENCES bins (bin_id) ON DELETE CASCADE
        );
        INSERT INTO items SELECT item_id, bin_id, name, category, quantity, item_photo, tags FROM _items_old;
        DROP TABLE _items_old;
        COMMIT;
        PRAGMA foreign_keys = ON;
    """)


def _migrate_v2(conn: sqlite3.Connection):
    """Migration 2: add version column for optimistic locking on items."""
    try:
        conn.execute("ALTER TABLE items ADD COLUMN version INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # already exists


def _migrate_v3(conn: sqlite3.Connection):
    """Migration 3: add audit_log and sync_conflicts tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            actor      TEXT NOT NULL,
            action     TEXT NOT NULL,
            item_id    INTEGER,
            details    TEXT,
            timestamp  TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id    INTEGER NOT NULL,
            bin_id     TEXT,
            name       TEXT,
            category   TEXT,
            quantity   INTEGER,
            source     TEXT NOT NULL DEFAULT 'sheets',
            resolved   INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)


def init_db():
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bins (
            bin_id TEXT PRIMARY KEY,
            zone TEXT NOT NULL,
            shelf_number TEXT,
            color_code TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id TEXT,
            name TEXT NOT NULL,
            category TEXT,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (bin_id) REFERENCES bins (bin_id)
        )
    """)
    conn.commit()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_colors (
            tag_name TEXT PRIMARY KEY,
            hex TEXT NOT NULL
        )
    """)
    conn.commit()

    # Schema version tracker — enables safe incremental migrations.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    applied = {r[0] for r in conn.execute("SELECT version FROM _schema_version").fetchall()}

    # Migration registry: versioned migration functions, no raw ALTER TABLE
    # outside this registry. Each migration is idempotent and runs once.
    MIGRATIONS = [
        (1, _migrate_v1),
        (2, _migrate_v2),
        (3, _migrate_v3),
    ]
    for version, fn in MIGRATIONS:
        if version not in applied:
            fn(conn)
            conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (version,))
            conn.commit()
            print(f"Applied migration v{version}")

    conn.close()


init_db()


def sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    name = re.sub(r"[^a-zA-Z0-9._-]", "", name)
    return name or "file"


def trigger_n8n_sync(bin_id: str, name: str, category: str, quantity: int, item_id: int | None = None):
    """Sends background webhook notification to n8n for Google Sheets sync."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT zone, shelf_number FROM bins WHERE bin_id = ?", (bin_id,))
    bin_info = cursor.fetchone()
    conn.close()

    bin_url = f"{BASE_URL}/bin/{urllib.parse.quote(bin_id)}"
    payload = {
        "bin_id": bin_id,
        "name": name,
        "category": category,
        "quantity": quantity,
        "item_id": item_id,
        "zone": bin_info["zone"] if bin_info else "Unknown",
        "shelf": bin_info["shelf_number"] if bin_info else "Unknown",
        "bin_url": bin_url,
        "qr_url": (
            f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(bin_url, safe='')}"
        ),
    }
    if not N8N_WEBHOOK_URL:
        return
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5, verify=False)
        print(f"n8n Sync Status: {response.status_code}")
    except Exception as e:
        print(f"Could not forward data to n8n webhook: {e}")


@app.post("/api/bulk-tag")
async def bulk_tag(request: Request):
    require_admin(request)
    data = await request.json()
    item_ids = [int(i) for i in data.get("item_ids", []) if str(i).isdigit()]
    tags = [t.strip().lower() for t in data.get("tags", []) if t.strip()]
    if not item_ids or not tags:
        return JSONResponse({"error": "item_ids and tags required"}, status_code=400)
    mode = data.get("mode", "add")
    conn = get_db()
    try:
        conn.execute("BEGIN")
        for item_id in item_ids:
            row = conn.execute("SELECT tags FROM items WHERE item_id=?", (item_id,)).fetchone()
            if not row:
                continue
            existing = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
            if mode == "remove":
                merged = [t for t in existing if t not in tags]
            else:
                merged = list(dict.fromkeys(existing + tags))
            conn.execute("UPDATE items SET tags=? WHERE item_id=?", (",".join(merged), item_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        # Audit after commit/close so the row is its own transaction and can't
        # be lost when the connection shuts down.
        for iid in item_ids:
            log_audit(conn, request, f"bulk-tag-{mode}", iid, f"tags={','.join(tags)}")
        conn.close()
    return JSONResponse({"ok": True, "updated": len(item_ids)})


@app.get("/api/tag-colors")
async def get_tag_colors():
    conn = get_db()
    rows = conn.execute("SELECT tag_name, hex FROM tag_colors").fetchall()
    conn.close()
    return {r["tag_name"]: r["hex"] for r in rows}


@app.post("/api/tag-colors")
async def set_tag_color(request: Request):
    require_admin(request)
    data = await request.json()
    tag = str(data.get("tag", "")).strip().lower()
    hex_val = str(data.get("hex", "")).strip()
    if not tag or not hex_val.startswith("#"):
        return JSONResponse({"error": "tag and hex required"}, status_code=400)
    conn = get_db()
    conn.execute(
        "INSERT INTO tag_colors (tag_name, hex) VALUES (?, ?) ON CONFLICT(tag_name) DO UPDATE SET hex=excluded.hex",
        (tag, hex_val),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


@app.get("/api/bins")
async def api_get_bins():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bins ORDER BY bin_id")
    bins = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for b in bins:
        deep_link = f"{BASE_URL}/bin/{urllib.parse.quote(b['bin_id'])}"
        b["qr_url"] = (
            f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(deep_link, safe='')}"
        )
    return bins


@app.get("/api/items")
async def api_get_items(search: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    if search:
        cursor.execute(
            """
            SELECT items.*, bins.zone, bins.shelf_number, bins.color_code
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            WHERE items.name LIKE ? OR items.category LIKE ? OR items.bin_id LIKE ? OR items.tags LIKE ?
            ORDER BY items.bin_id, items.name
            """,
            (f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"),
        )
    else:
        cursor.execute("""
            SELECT items.*, bins.zone, bins.shelf_number, bins.color_code
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            ORDER BY items.bin_id, items.name
            """)
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


@app.get("/login")
async def login(request: Request):
    if not AUTHENTIK_CLIENT_ID:
        return RedirectResponse("/")
    redirect_uri = BASE_URL.rstrip("/") + "/auth/callback"
    return await oauth.authentik.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    import time as _time

    token = await oauth.authentik.authorize_access_token(request)
    user = token.get("userinfo") or await oauth.authentik.userinfo(token=token)
    user_dict = dict(user)
    # Extract user identity for audit logging and per-user isolation.
    # Authentik returns groups as a list of group names in the "groups" claim.
    groups = user_dict.get("groups") or []
    if isinstance(groups, str):
        groups = [groups]
    request.session["user"] = {
        "sub": user_dict.get("sub") or user_dict.get("username"),
        "email": user_dict.get("email", ""),
        "name": user_dict.get("name") or user_dict.get("preferred_username") or user_dict.get("username", ""),
        "groups": groups,
    }

    # ---- Email gate (v1.2.2) ----
    email = request.session["user"]["email"].strip().lower()
    allowed = [e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()]
    blocked = [e.strip().lower() for e in os.environ.get("BLOCKED_EMAILS", "").split(",") if e.strip()]

    # Track per-IP attempt count for backoff
    ip = request.client.host
    now = _time.time()
    attempts = _attempts.get(ip, {"count": 0, "first_ts": now, "last_ts": now})
    attempts["count"] += 1
    attempts["last_ts"] = now
    _attempts[ip] = attempts

    # Delay before responding (denies timing side-channel)
    if attempts["count"] >= 5:
        delay = 60
    elif attempts["count"] >= 4:
        delay = 30
    elif attempts["count"] >= 3:
        delay = 15
    elif attempts["count"] >= 2:
        delay = 5
    else:
        delay = 0
    _time.sleep(delay)

    if allowed and email not in allowed:
        # Whitelist active and email doesn't match → deny
        request.session.clear()
        return JSONResponse({"error": "email not in allowed list"}, status_code=403)

    if not allowed and email in blocked:
        # Whitelist off, but blacklist on → deny
        request.session.clear()
        return JSONResponse({"error": "email on blocked list"}, status_code=403)

    # Email passes — now check admin group, but only if ADMIN_GROUP is configured.
    # If ADMIN_GROUP is empty/unconfigured, skip the admin check (backward-compatible).
    is_admin = bool(ADMIN_GROUP) and (ADMIN_GROUP in groups)

    # ---- End email gate ----

    request.session["is_admin"] = is_admin


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, search: str = ""):
    auth = _require_auth_html(request)
    if isinstance(auth, RedirectResponse):
        return auth
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bins")
    bins = [dict(row) for row in cursor.fetchall()]

    for b in bins:
        deep_link = f"{BASE_URL}/bin/{urllib.parse.quote(b['bin_id'])}"
        b["qr_url"] = (
            f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(deep_link, safe='')}"
        )

    if search:
        cursor.execute(
            """
            SELECT items.*, bins.zone, bins.shelf_number
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            WHERE items.name LIKE ? OR items.category LIKE ?
            """,
            (f"%{search}%", f"%{search}%"),
        )
    else:
        cursor.execute("""
            SELECT items.*, bins.zone, bins.shelf_number
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            """)
    items = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bins": bins,
            "items": items,
            "search": search,
            "single_bin": None,
            "t": _LOCALE,
            "locale_json": json.dumps(_LOCALE, ensure_ascii=False),
            "user": request.session.get("user"),
            "oidc_enabled": bool(AUTHENTIK_CLIENT_ID),
        },
    )


@app.get("/bin/{bin_id}", response_class=HTMLResponse)
async def view_single_bin(request: Request, bin_id: str):
    """Deep-link endpoint hit when scanning physical box labels with phone."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bins WHERE bin_id = ?", (bin_id,))
    target_bin = cursor.fetchone()

    cursor.execute("SELECT * FROM items WHERE bin_id = ?", (bin_id,))
    items = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bins": [],
            "items": items,
            "search": "",
            "single_bin": target_bin,
            "t": _LOCALE,
            "locale_json": json.dumps(_LOCALE, ensure_ascii=False),
        },
    )


@app.post("/add-bin")
async def web_add_bin(
    request: Request,
    bin_id: str = Form(...),
    zone: str = Form(...),
    room: str = Form(""),
    shelf: str = Form(...),
    color: str = Form(...),
):
    require_admin(request)
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO bins (bin_id, zone, room, shelf_number, color_code) VALUES (?, ?, ?, ?, ?)",
            (bin_id, zone, room, shelf, color),
        )
        conn.commit()
        log_audit(conn, request, "create-bin", None, f"bin_id={bin_id}, zone={zone}")
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": f"Box ID '{bin_id}' already exists"}, status_code=400)
    finally:
        conn.close()
    return JSONResponse({"ok": True, "bin_id": bin_id})


@app.post("/add-item")
async def web_add_item(
    request: Request,
    background_tasks: BackgroundTasks,
    bin_id: str = Form(...),
    name: str = Form(...),
    category: str = Form(...),
    qty: int = Form(...),
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (bin_id, name, category, quantity) VALUES (?, ?, ?, ?)",
        (bin_id, name, category, qty),
    )
    item_id = cursor.lastrowid
    conn.commit()
    log_audit(conn, request, "create-item", item_id, f"bin_id={bin_id}, name={name}, category={category}, qty={qty}")
    conn.close()
    background_tasks.add_task(trigger_n8n_sync, bin_id, name, category, qty, item_id)
    return JSONResponse({"ok": True, "item_id": item_id})


@app.post("/api/move-items")
async def move_items(request: Request):
    require_admin(request)
    data = await request.json()
    item_ids = [int(i) for i in data.get("item_ids", []) if str(i).isdigit()]
    target_bin = str(data.get("bin_id", "")).strip()
    if not item_ids or not target_bin:
        return JSONResponse({"error": "item_ids and bin_id required"}, status_code=400)
    conn = get_db()
    try:
        conn.execute("BEGIN")
        if not conn.execute("SELECT 1 FROM bins WHERE bin_id=?", (target_bin,)).fetchone():
            conn.rollback()
            return JSONResponse({"error": f"Bin '{target_bin}' not found"}, status_code=404)
        placeholders = ",".join("?" * len(item_ids))
        conn.execute(
            f"UPDATE items SET bin_id=? WHERE item_id IN ({placeholders})",
            [target_bin] + item_ids,
        )
        conn.commit()
        for iid in item_ids:
            log_audit(conn, request, "move-item", iid, f"target_bin={target_bin}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return JSONResponse({"ok": True, "moved": len(item_ids)})


@app.patch("/update-bin/{bin_id}")
async def update_bin(bin_id: str, request: Request):
    require_admin(request)
    data = await request.json()
    zone = str(data.get("zone", "")).strip()
    room = str(data.get("room", "")).strip()
    shelf = str(data.get("shelf", "")).strip()
    color = str(data.get("color", "")).strip()
    if not zone or not shelf or not color:
        return JSONResponse({"error": "zone, shelf, and color are required"}, status_code=400)
    conn = get_db()
    conn.execute(
        "UPDATE bins SET zone=?, room=?, shelf_number=?, color_code=? WHERE bin_id=?",
        (zone, room, shelf, color, bin_id),
    )
    conn.commit()
    log_audit(conn, request, "update-bin", None, f"bin_id={bin_id}, zone={zone}, room={room}, shelf={shelf}")
    conn.close()
    return JSONResponse({"ok": True})


@app.delete("/delete-bin/{bin_id}")
async def delete_bin(bin_id: str, request: Request):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM items WHERE bin_id = ?", (bin_id,))
    if cursor.fetchone()["c"] > 0:
        conn.close()
        return JSONResponse(
            {"error": "Remove all items from this box before deleting it."},
            status_code=400,
        )
    cursor.execute("SELECT bin_photo FROM bins WHERE bin_id = ?", (bin_id,))
    row = cursor.fetchone()
    if row and row["bin_photo"]:
        p = PHOTOS_DIR / row["bin_photo"]
        if p.exists():
            p.unlink()
    conn.execute("DELETE FROM bins WHERE bin_id = ?", (bin_id,))
    conn.commit()
    log_audit(conn, request, "delete-bin", None, f"bin_id={bin_id}")
    conn.close()
    return JSONResponse({"ok": True})


@app.patch("/update-item/{item_id}")
async def update_item(item_id: int, request: Request):
    require_admin(request)
    data = await request.json()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "")).strip()
    try:
        quantity = int(data.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1
    tags = ",".join(t.strip().lower() for t in str(data.get("tags", "")).split(",") if t.strip())
    if not name or not category:
        return JSONResponse({"error": "name and category required"}, status_code=400)
    # NEW: optimistic locking — fetch current version and check it before update
    conn = get_db()
    current = conn.execute(
        "SELECT name, category, quantity, version FROM items WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    if not current:
        conn.close()
        return JSONResponse({"error": "item not found"}, status_code=404)
    # Optimistic lock: the client MUST send the version it last read. If it
    # omits the field, the check is vacuous — every edit would "succeed" and
    # concurrent writes would still silently overwrite each other.
    incoming_version = data.get("version")
    if incoming_version is None:
        conn.close()
        return JSONResponse(
            {"error": "version required — re-fetch the item and retry"},
            status_code=400,
        )
    try:
        incoming_version = int(incoming_version)
    except (ValueError, TypeError):
        conn.close()
        return JSONResponse({"error": "invalid version"}, status_code=400)
    # Attempt update only if version matches; SQLite rows_affected tells us success
    cursor = conn.execute(
        "UPDATE items SET name=?, category=?, quantity=?, tags=?, version=version+1 WHERE item_id=? AND version=?",
        (name, category, quantity, tags, item_id, incoming_version),
    )
    conn.commit()
    rows_affected = cursor.rowcount if hasattr(cursor, "rowcount") else 0
    if rows_affected == 0:
        conn.close()
        # Version mismatch — another user edited this item first
        return JSONResponse(
            {"error": "stale version — another user edited this item", "current_version": current["version"]},
            status_code=409,
        )
    # Read the post-update version rather than trusting current["version"]+1:
    # current is the pre-update snapshot, so +1 is only correct when no other
    # writer has touched the row since the SELECT.
    new_version = conn.execute("SELECT version FROM items WHERE item_id = ?", (item_id,)).fetchone()
    conn.close()
    return JSONResponse({"ok": True, "new_version": new_version["version"] if new_version else None})


@app.delete("/delete-item/{item_id}")
async def delete_item(item_id: int, request: Request):
    require_admin(request)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT item_photo FROM items WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    if row and row["item_photo"]:
        p = PHOTOS_DIR / row["item_photo"]
        if p.exists():
            p.unlink()
    conn.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
    conn.commit()
    log_audit(conn, request, "delete-item", item_id, f"item_id={item_id}")
    conn.close()
    return JSONResponse({"ok": True})


@app.post("/upload-photo/{photo_type}/{record_id}")
async def upload_photo(request: Request, photo_type: str, record_id: str, file: UploadFile = File(...)):
    require_admin(request)
    if photo_type not in {"item", "bin"}:
        raise HTTPException(status_code=400, detail="Invalid upload type; must be 'item' or 'bin'")
    safe_name = sanitize_filename(file.filename or "")
    ext = Path(safe_name).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
        ext = ".jpg"
    filename = f"{photo_type}_{record_id}_{int(time.time())}{ext}"
    filepath = PHOTOS_DIR / filename
    filepath.write_bytes(await file.read())

    conn = get_db()
    cursor = conn.cursor()
    if photo_type == "item":
        cursor.execute("SELECT item_photo FROM items WHERE item_id = ?", (record_id,))
        old = cursor.fetchone()
        if old and old["item_photo"]:
            p = PHOTOS_DIR / old["item_photo"]
            if p.exists():
                p.unlink()
        conn.execute("UPDATE items SET item_photo = ? WHERE item_id = ?", (filename, record_id))
    else:
        cursor.execute("SELECT bin_photo FROM bins WHERE bin_id = ?", (record_id,))
        old = cursor.fetchone()
        if old and old["bin_photo"]:
            p = PHOTOS_DIR / old["bin_photo"]
            if p.exists():
                p.unlink()
        conn.execute("UPDATE bins SET bin_photo = ? WHERE bin_id = ?", (filename, record_id))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "filename": filename})


@app.get("/photos/{filename}")
async def serve_photo(filename: str):
    filepath = PHOTOS_DIR / sanitize_filename(filename)
    if not filepath.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(str(filepath))


@app.post("/api/sync-row")
async def sync_row_from_sheet(request: Request):
    """Called by n8n to create items sourced from Google Sheets (no webhook fired to avoid loop).

    Auth: N8N_WEBHOOK_SECRET query parameter. Acts as SERVICE_USER_SUB.
    Payload: bin_id, name, category, quantity, zone, shelf, item_id, mode ("create"|"update")
    """
    # --- Webhook secret check (v1.2.2) ---
    secret = request.query_params.get("N8N_WEBHOOK_SECRET", "").strip()
    if not N8N_WEBHOOK_SECRET or secret != N8N_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="invalid webhook secret")

    # Service user identity (bypasses email gate)
    actor = SERVICE_USER_SUB

    data = await request.json()
    mode = data.get("mode", "create")  # "create" or "update"
    bin_id = str(data.get("bin_id", "")).strip()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "")).strip()
    try:
        quantity = int(float(str(data.get("quantity", 1))))
    except (ValueError, TypeError):
        quantity = 1
    zone = str(data.get("zone", "")).strip() or "Unknown"
    shelf = str(data.get("shelf", "")).strip() or "Unknown"
    item_id = data.get("item_id")

    if not bin_id or not name or not category:
        return JSONResponse({"error": "bin_id, name, and category are required"}, status_code=400)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT bin_id FROM bins WHERE bin_id = ?", (bin_id,))
    if not cursor.fetchone():
        conn.execute(
            "INSERT INTO bins (bin_id, zone, shelf_number, color_code) VALUES (?, ?, ?, ?)",
            (bin_id, zone, shelf, "Unknown"),
        )
        conn.commit()

    # --- Update path (v1.2.2) ---
    if mode == "update":
        if item_id is None:
            return JSONResponse({"error": "item_id required for mode=update"}, status_code=400)
        try:
            item_id_int = int(item_id)
        except (ValueError, TypeError):
            return JSONResponse({"error": "invalid item_id"}, status_code=400)

        # Verify item exists
        existing = cursor.execute("SELECT item_id FROM items WHERE item_id = ?", (item_id_int,)).fetchone()
        if not existing:
            return JSONResponse({"error": "item not found"}, status_code=404)

        # Optimistic locking if version provided
        incoming_version = data.get("version")
        if incoming_version is not None:
            try:
                incoming_version = int(incoming_version)
            except (ValueError, TypeError):
                return JSONResponse({"error": "invalid version"}, status_code=400)

            cursor = conn.execute(
                "UPDATE items SET name=?, category=?, quantity=?, tags=?, version=version+1 WHERE item_id=? AND version=?",
                (name, category, quantity, data.get("tags", ""), item_id_int, incoming_version),
            )
            conn.commit()
            if cursor.rowcount == 0:
                conn.close()
                return JSONResponse(
                    {"error": "stale version — another user edited this item"},
                    status_code=409,
                )
        else:
            conn.execute(
                "UPDATE items SET name=?, category=?, quantity=?, tags=? WHERE item_id=?",
                (name, category, quantity, data.get("tags", ""), item_id_int),
            )
            conn.commit()

        # Conflict detection — if sheet row differs from app row, log to sync_conflicts
        existing = cursor.execute("SELECT quantity, category FROM items WHERE item_id = ?", (item_id_int,)).fetchone()
        if existing and existing != (quantity, category):
            conn.execute(
                """INSERT INTO sync_conflicts (item_id, bin_id, name, category, quantity, source, resolved)
                   VALUES (?, ?, ?, ?, ?, 'sheets', 0)""",
                (item_id_int, bin_id, name, category, quantity),
            )
            conn.commit()

        # Audit
        conn.execute(
            """INSERT INTO audit_log (actor, action, item_id, details, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (actor, "sync-row-update", item_id_int, f"bin_id={bin_id}, name={name}", datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
        print(f"Sheet→App sync: '{name}' x{quantity} → {bin_id} (item_id={item_id_int}, UPDATED)")
        return JSONResponse({"ok": True, "item_id": item_id_int, "updated": True})

    # --- Create path (existing, with append-only idempotency) ---
    if item_id is not None:
        try:
            item_id_int = int(item_id)
        except (ValueError, TypeError):
            item_id_int = None
    else:
        item_id_int = None

    if item_id_int is not None:
        existing = cursor.execute("SELECT item_id FROM items WHERE item_id = ?", (item_id_int,)).fetchone()
        if existing:
            # Item already exists; skip insert, log sync conflict, return ok
            conn.execute(
                """INSERT INTO audit_log (actor, action, item_id, details, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    actor,
                    "sync-row-skip-existing",
                    item_id_int,
                    f"bin_id={bin_id}, name={name}",
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
            print(f"Sheet→App sync: '{name}' x{quantity} → {bin_id} (item_id={item_id_int}, SKIPPED — already exists)")
            return JSONResponse({"ok": True, "item_id": item_id_int, "skipped": True})

    cursor.execute(
        "INSERT INTO items (bin_id, name, category, quantity) VALUES (?, ?, ?, ?)",
        (bin_id, name, category, quantity),
    )
    new_item_id = cursor.lastrowid
    conn.commit()

    # Always log sync to audit_log
    conn.execute(
        """INSERT INTO audit_log (actor, action, item_id, details, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (
            actor,
            "sync-row-create",
            new_item_id,
            f"bin_id={bin_id}, name={name}, quantity={quantity}",
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    print(f"Sheet→App sync: '{name}' x{quantity} → {bin_id} (item_id={new_item_id})")
    return JSONResponse({"ok": True, "item_id": new_item_id})


@app.get("/api/backup")
async def backup_database():
    """Download a point-in-time snapshot of the SQLite database."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"/tmp/kapaat-backup-{ts}.db"
    src = get_db()
    dst = sqlite3.connect(backup_path)
    src.backup(dst)
    dst.close()
    src.close()
    return FileResponse(
        backup_path,
        filename=f"kapaat-backup-{ts}.db",
        media_type="application/octet-stream",
    )


@app.get("/api/backup/download")
async def download_full_backup():
    """Stream a zip archive containing the live DB snapshot and all photos."""
    import tempfile

    zip_buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(DB_NAME):
                with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    src = get_db()
                    dst = sqlite3.connect(tmp_path)
                    src.backup(dst)
                    dst.close()
                    src.close()
                    zf.write(tmp_path, "garage_inventory.db")
                finally:
                    os.unlink(tmp_path)
            if PHOTOS_DIR.exists():
                for file_path in PHOTOS_DIR.rglob("*"):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(PHOTOS_DIR.parent))
                        zf.write(str(file_path), arcname)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}") from e
    # Prune old backups after a successful download — retention is enforced
    # here, not only on manual trigger, so a forgotten /api/backup/retention
    # call never lets archives pile up.
    try:
        await backup_retention()
    except Exception:
        pass
    zip_buffer.seek(0)
    filename = f"kapaat_backup_{datetime.now().strftime('%Y-%m-%d_%H%M')}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/backup/retention")
async def backup_retention():
    """List and auto-prune backup archives in /data/backups/."""
    backups_dir = Path("/data/backups")
    backups_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(backups_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Keep last 10 backups by default
    keep = 10
    pruned = []
    for f in files[keep:]:
        try:
            f.unlink()
            pruned.append(f.name)
        except Exception:
            pass
    return JSONResponse(
        {
            "kept": [f.name for f in files[:keep]],
            "pruned": pruned,
            "retention_limit": keep,
        }
    )


@app.post("/api/backup/retention")
async def backup_retention_post(request: Request):
    require_admin(request)
    """Manual trigger for backup pruning."""
    return await backup_retention()


@app.get("/api/sync-conflicts")
async def sync_conflicts(request: Request):
    """Return unresolved sync conflicts for the dashboard banner."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, item_id, bin_id, name, category, quantity, source, created_at "
        "FROM sync_conflicts WHERE resolved = 0 ORDER BY created_at DESC"
    )
    conflicts = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return JSONResponse({"conflicts": conflicts})


@app.post("/api/sync-conflicts/{conflict_id}/resolve")
async def resolve_sync_conflict(conflict_id: int, request: Request):
    require_admin(request)
    """Mark a sync conflict as resolved."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE sync_conflicts SET resolved = 1 WHERE id = ?", (conflict_id,))
    if cursor.rowcount == 0:
        conn.close()
        return JSONResponse({"error": "conflict not found"}, status_code=404)
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


@app.get("/manifest.json")
async def pwa_manifest():
    name = os.environ.get("APP_TITLE", "Kapaat")
    return JSONResponse(
        {
            "name": f"{name} — Garage Bin Inventory",
            "short_name": name,
            "description": "Track what's inside every storage box, where it lives, and find it fast.",
            "start_url": "/",
            "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#0b1326",
            "theme_color": "#4cd7f6",
            "icons": [
                {"src": "/static/icon.svg", "type": "image/svg+xml", "sizes": "any"},
                {
                    "src": "/static/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": "/static/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                },
            ],
        }
    )


@app.get("/sw.js")
async def service_worker():
    js = """
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(clients.claim()));
self.addEventListener("fetch", e => {
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
""".strip()
    from fastapi.responses import Response

    return Response(content=js, media_type="application/javascript")


@app.get("/export/{file_type}")
async def export_data(file_type: str):
    conn = get_db()
    df = pd.read_sql_query(
        """
        SELECT items.name, items.category, items.quantity,
               bins.bin_id, bins.zone, bins.shelf_number
        FROM items JOIN bins ON items.bin_id = bins.bin_id
        """,
        conn,
    )
    conn.close()

    filepath = f"/tmp/garage_inventory.{'csv' if file_type == 'csv' else 'xlsx'}"
    if file_type == "csv":
        df.to_csv(filepath, index=False)
    else:
        df.to_excel(filepath, index=False)
    return FileResponse(filepath, filename=os.path.basename(filepath))
