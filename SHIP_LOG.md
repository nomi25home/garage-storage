# Ship Log — kapaat

Running log of completed issues/enhancements, appended per `/ship` invocation.
Format: one entry per shipped change, most recent at top.

---

## 2026-10-22 — P2 hardening: close 3 P1 defects from CEO review

**PR:** #2 (`ship-p2-hardening-20261022`) — https://github.com/nomi25home/kapaat/pull/2
**Base:** main | **Version:** 1.2.0 → 1.2.1

### P1 defects closed (CEO review → Eng Review)
- **P1#2** — `/api/sync-row` idempotency: incoming `item_id` that already exists is now skipped instead of inserting a duplicate row. Logged as `sync-row-skip-existing`.
- **P1#3** — sync-conflict dashboard banner: `templates/index.html` polls `/api/sync-conflicts` on load, shows a banner with per-conflict "Mark resolved" buttons.
- **P1#4** — backup retention auto-prune: `download_full_backup()` calls `backup_retention()` at the end, so retention is enforced on every download, not only on manual trigger.

### Related fixes
- `log_audit()` now commits its own row. It was called after `conn.commit()` in `delete_item`, so the audit row was silently rolled back when the connection closed — the delete read as unaudited.
- `bulk_tag` audit calls moved to the `finally` block so they survive a rollback.
- `update_item` optimistic locking now rejects a missing `version` field (400) instead of silently succeeding — the lock was vacuous before.

## 2026-10-23 — v1.2.2: multi-user access control

**PR:** #3 (`ship-p2-hardening-20261022`) — https://github.com/nomi25home/kapaat/pull/3
**Base:** main | **Version:** 1.2.1 → 1.2.2

### P1 defects closed
- Email gate at login: `ALLOWED_EMAILS`/`BLOCKED_EMAILS`; blocklist wins; all users must pass → 403
- Backoff algorithm per-IP on auth failures: 0s → 5s → 15s → 30s → 60s capped, denies timing side-channel
- Admin = Authentik group (`ADMIN_GROUP`), checked at login + on every mutating route; revocable group membership

### v1.2.2 features added
- Email gate enforcement on `/auth/callback` with `ALLOWED_EMAILS` whitelist and `BLOCKED_EMAILS` blacklist
- Per-IP backoff delays before auth failure 403 responses
- `require_admin()` on 11 mutating routes (`bulk_tag`, `tag-colors`, `add-bin`, `add-item`, `move-items`, `update-bin`, `delete-bin`, `update-item`, `delete-item`, `upload-photo`, `sync-row`)
- `/api/sync-row` hardened: `N8N_WEBHOOK_SECRET` query param; `mode=update` path with optimistic locking + conflict detection
- Conflict detection populates `sync_conflicts` table; `/api/sync-conflicts` banner shows real mismatches
- sync-row idempotency: `item_id` already exists → skip, log `sync-row-skip-existing`

### v1.2.2 changes
- Non-admins are view-only; admins may edit. Email gate applies to everyone.
- `sync_conflicts` table populated on actual conflicts; no longer dead.
- `N8N_WEBHOOK_SECRET`, `SERVICE_USER_SUB` env vars; admin group configurable via `ADMIN_GROUP`
- Backoff algorithm on auth failures capped at 60s

### Tests
`tests/test_hardening.py` — 7/7 pass:
- sync-row idempotency (no duplicate rows)
- sync-row create logs audit
- optimistic lock conflict (stale version → 409)
- update_item requires version (400)
- delete-item logs audit
- backup retention prunes to limit
- non-admin denied on mutating routes

### Verification
- `pytest tests/` — 7 passed
- `ruff check app.py` — all checks passed

### Notes
- `tests/conftest.py` `admin_client` fixture rebuilt to use `itsdangerous.TimestampSigner` (matching Starlette SessionMiddleware signing) instead of deprecated `URLSafeTimedSerializer`
- LOCALE_DIR repointed at repo's `locales/` from temp dir
- Added `autouse=True` `_reset_db` fixture
- `tests/test_backup_retention_prunes` patches `app.Path` so `/data/backups` lands in `tmp_path`
- `ALLOWED_EMAILS`, `BLOCKED_EMAILS`, `ADMIN_GROUP`, `N8N_WEBHOOK_SECRET`, `SERVICE_USER_SUB` documented in `.env.example`