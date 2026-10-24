# v1.2.2 Design Doc — Multi-User Access Control

**Branch:** `ship-p2-hardening-20261022` | **Version:** 1.2.1 → 1.2.2 | **Goal:** Add email-gated access control to the existing Authentik OIDC login, turn `groups` into admin role, and harden the sheet sync endpoint.

---

## Premises (all agreed — 7 items)

1. **User identity = Authentik `sub`.** Stable per-user; not the display name, not the email.
2. **Access control, not data partitioning.** One shared inventory. Everyone sees the same items/bins. Non-admins are view-only; admins can edit.
3. **Admin = Authentik group** (`ADMIN_GROUP` env var, default `admins`), checked at login and on every mutating request. Admin status is revocable — change the group membership in Authentik, and the next login revokes it immediately.
4. **Email gate: whitelist first, blacklist second.** `ALLOWED_EMAILS` (comma-separated) and `BLOCKED_EMAILS` (comma-separated).
   - If `ALLOWED_EMAILS` is set (non-empty), the user's login email must match one of them.
   - If `ALLOWED_EMAILS` is empty/not set, the user's email must NOT appear in `BLOCKED_EMAILS`.
   - Blocklist wins if both are set.
   - Non-matching email → 403 at login, before any session data is created.
5. **All users must pass the email gate.** Even admins. The email check runs **before** the group check — an admin whose email is blocked is denied.
6. **Sheet sync service identity.** `/api/sync-row` authenticates via `N8N_WEBHOOK_SECRET` query parameter, acts as `SERVICE_USER_SUB`, **bypasses** the email list. It's a machine, not a person.
7. **Community API is v1.2.3**, read-only catalog built on top of this boundary. Not in this release.

---

## Login flow changes

### New env vars

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `ALLOWED_EMAILS` | comma-separated list | `""` (empty = disabled) | If non-empty, user's login email must match one of these |
| `BLOCKED_EMAILS` | comma-separated list | `""` (empty = disabled) | User's email must NOT appear in this list |
| `ADMIN_GROUP` | single group name | `"admins"` | Authentik group whose members are admins |
| `N8N_WEBHOOK_SECRET` | secret string | `""` | Shared secret for `/api/sync-row` webhook |
| `SERVICE_USER_SUB` | string | `"service-user"` | Sub value for authenticated sheet-sync requests |

### Email gate (at `/auth/callback`)

After Authentik OIDC callback completes and `request.session["user"]` is set, run:

```python
email = request.session["user"]["email"].strip().lower()
allowed = [e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()]
blocked = [e.strip().lower() for e in os.environ.get("BLOCKED_EMAILS", "").split(",") if e.strip()]

if allowed and email not in allowed:
    # Whitelist is active and email doesn't match → deny
    request.session.clear()
    return JSONResponse({"error": "email not in allowed list"}, status_code=403)

if not allowed and email in blocked:
    # Whitelist off, but blacklist on → deny
    request.session.clear()
    return JSONResponse({"error": "email on blocked list"}, status_code=403)

# Email passes — now check admin group
user_groups = request.session["user"].get("groups", [])
is_admin = ADMIN_GROUP in user_groups
```

If email denied → return 403 with generic message; **do not** reveal whether the gate is whitelist or blacklist.

### Backoff algorithm for malicious auth attempts (per-IP, in-memory)

Track attempts in a dict that resets on app restart:

```python
# At module level, near the top of app.py
_attempts: dict[str, dict] = {}  # ip → {"count": int, "first_ts": float, "last_ts": float}

# In the auth_callback, after failed email check (before session.clear()):
ip = request.client.host
now = time.time()
attempts = _attempts.get(ip, {"count": 0, "first_ts": now, "last_ts": now})
attempts["count"] += 1
attempts["last_ts"] = now
_attempts[ip] = attempts

# Delay before responding (mimics "correct" auth delay regardless of outcome)
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

# Sleep briefly before the 403 (mimic "real" auth regardless of outcome)
time.sleep(delay)
```

The delay caps at 60s; every subsequent failure just sleeps 60s. The sleep is *before* returning the 403, so the total request time is always `auth_time + delay` — this denies the attacker a timing side-channel.

### Enforcement on mutating routes

Add a dependency: before any `PATCH`, `POST`, or `DELETE` route runs, check `request.session.get("user")` and `is_admin`. If the user is not admin → 403. The email gate already ran at login, so this just checks the admin flag.

---

## Admin enforcement

### At login (revocable)

After the email gate passes, check:

```python
user_groups = request.session["user"].get("groups", [])
is_admin = ADMIN_GROUP in user_groups
store `is_admin` in the session for the request duration
```

### On every mutating route

Add a tiny dependency at the top of each `PATCH`, `POST`, `DELETE`:

```python
if not request.session.get("is_admin"):
    return JSONResponse({"error": "admin required"}, status_code=403)
```

This is a **runtime check**, not a cache — the session is per-request in FastAPI's stateless model. Changing group membership in Authentik takes effect at the next login.

---

## Sheet sync hardening

### New query parameter

`/api/sync-row?N8N_WEBHOOK_SECRET=<secret>` — must match the env var `N8N_WEBHOOK_SECRET`. If missing or wrong → 403.

### Authenticated identity

The webhook acts as `SERVICE_USER_SUB` (env var, default `"service-user"`). This identity:

- Bypasses the email gate entirely
- Is the `actor` in audit_log entries
- Can be inspected by the community API (read-only)

### Add an update path

Extend `/api/sync-row` to handle a `"mode": "update"` payload:

```python
if mode == "update":
    # Update existing item: name, category, quantity from payload
    # If the item's owner_sub != SERVICE_USER_SUB → 403
    # If version field present → optimistic locking check
    # Log to sync_conflicts if quantity changed vs. what app had
```

### Conflict detection (finally alive)

When a sheet row's `name` + `bin_id` + `quantity` differ from the existing app row, write to `sync_conflicts`:

```python
existing = conn.execute("SELECT quantity, category FROM items WHERE bin_id=? AND name=?", (bin_id, name)).fetchone()
if existing and existing != (quantity, category):
    conn.execute(
        """INSERT INTO sync_conflicts (item_id, bin_id, name, category, quantity, source, resolved)
           VALUES (?, ?, ?, ?, ?, 'sheets', 0)""",
        (item_id, bin_id, name, category, quantity),
    )
    conn.commit()
```

The `/api/sync-conflicts` banner will now actually show mismatches.

---

## v1.2.3 community API (outline — deferred)

Read-only public surface:

- `GET /api/community/tools` — list all tools (name, category, photo thumbnail URL, tag list)
- `GET /api/community/tools/{name}` — get one tool's detail
- No write endpoints. Tokens not required (public read). Rate-limited per IP.

Depends on the isolation boundary (v1.2.2) being stable first.

---

## Migration registry items (already in code — no-op for v1.2.2)

- Item 3 on the roadmap: ✅ already done. `_schema_version` + migration registry. No raw `ALTER TABLE` outside the registry. Closed.

---

## What's NOT in this release

- Per-user data partitioning. The inventory stays shared; isolation is read/admin only.
- Community API. That's v1.2.3, built on top of the v1.2.2 boundary.
- Any changes to the DB schema beyond what's already in `app.py` (items/bins tables unchanged).

---

## Files modified

- `app.py` — login flow, email gate, backoff, admin check on mutating routes, sync-row secret + update path + conflict detection
- `.env.example` — document new env vars (no secrets)
- `CHANGELOG.md` — unreleased entry (see below)
- `SHIP_LOG.md` — one entry appended

---

## CHANGELOG unreleased entry

## [1.2.2] — 2026-10-22

### Fixed
- Email gate at login: `ALLOWED_EMAILS` whitelist, `BLOCKED_EMAILS` blacklist; blocklist wins if both set; all users (including admins) must pass; non-matching → 403
- Backoff algorithm on repeated auth failures from one IP: 0s → 5s → 15s → 30s → 60s capped
- Admin = Authentik group (`ADMIN_GROUP`), checked at login and on every mutating request; email gate runs first
- `sync-row` now requires `N8N_WEBHOOK_SECRET` query parameter; acts as `SERVICE_USER_SUB`; bypasses email gate
- Added deterministic update path for `/api/sync-row` (mode=update); sheet→app sync now supports modifies, not just inserts
- Conflict detection now populates `sync_conflicts` table when sheet and app disagree; `/api/sync-conflicts` banner now shows real mismatches

### Changed
- Non-admins are view-only; admins may edit. Email gate applies to everyone.
- `sync_conflicts` table is no longer dead — it is populated on actual conflicts.

### Added
- `ALLOWED_EMAILS`, `BLOCKED_EMAILS` env vars (documented in `.env.example`)
- `ADMIN_GROUP` env var (default `admins`)
- `N8N_WEBHOOK_SECRET`, `SERVICE_USER_SUB` env vars
- Backoff delay on auth failures
- `sync_conflicts` population on `/api/sync-row` conflict

### Security
- Authentik group membership is revocable — change membership in Authentik, next login takes effect
- All auth failures sleep before responding, denying timing side-channels
- Whitelist is active only when non-empty; empty = whitelist off
- Blacklist wins over whitelist when both are configured