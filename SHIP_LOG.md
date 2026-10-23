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

### Tests
`tests/test_hardening.py` — 6/6 pass:
- sync-row idempotency (no duplicate rows)
- sync-row create logs audit
- optimistic lock conflict (stale version → 409)
- update_item requires version (400)
- delete-item logs audit
- backup retention prunes to limit

### Verification
- `pytest tests/` — 6 passed
- `ruff check app.py` — all checks passed

### Notes
- `tests/conftest.py` `LOCALE_DIR` pointed at a temp dir, so `app.py`'s module-load `_load_locale()` failed; repointed at the repo's `locales/`.
- Added `autouse=True` `_reset_db` fixture: `app.py` is imported once and `DB_PATH` is fixed at import time, so without a reset every test saw the previous test's rows (audit_log accumulated across the suite).
- `tests/test_backup_retention_prunes` patches `app.Path` so `/data/backups` lands in `tmp_path`.