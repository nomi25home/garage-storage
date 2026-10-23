# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.2.2] — 2026-10-23

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
- `test_non_admin_denied_on_mutating_route` test

### Security
- Authentik group membership is revocable — change membership in Authentik, next login takes effect
- All auth failures sleep before responding, denying timing side-channels
- Whitelist is active only when non-empty; empty = whitelist off
- Blacklist wins over whitelist when both are configured

---

## [1.2.1] — 2026-10-22

### Fixed
- `/api/sync-row` now honors an incoming `item_id`: if the item already exists it is skipped instead of inserting a duplicate row (`sync-row-skip-existing` audit entry).
- Dashboard banner now shows unresolved sync conflicts from `/api/sync-conflicts`, with per-conflict "Mark resolved" buttons.
- Backup retention is now enforced on every backup download, not only on manual `/api/backup/retention` trigger.
- Audit rows are no longer silently dropped: `log_audit()` commits its own row, and `bulk_tag` audit calls survive rollback.
- `PATCH /update-item/{id}` now rejects a missing or invalid `version` field (400) instead of silently succeeding — the optimistic lock is no longer vacuous.

### Added
- `audit_log` and `sync_conflicts` tables (migration v3).
- `version` column on `items` for optimistic locking (migration v2).
- Migration registry (`_migrate_v1`/`v2`/`v3`) — no raw `ALTER TABLE` outside the registry.
- `/api/backup/retention` and `/api/sync-conflicts` endpoints.

## [0.1.0] — 2025-10-20

### Added
- Multi-level location hierarchy: Zone → Room → Shelf → Bin
- Multi-select filter chips for Zone, Room, and Box
- Items table with photo thumbnails, name, category, qty, location, and tags
- Inline item editing (name, category, quantity, tags)
- Move items between bins — single item and bulk
- Bulk tag add / remove across multiple selected items
- Per-tag color coding with a swatch palette picker
- Tag filter (multi-select) in the filter bar
- Per-item and per-bin photo upload and full-screen zoom
- QR code labels per bin — print and mobile scan view
- Full-text search across name, category, box ID, and tags
- CSV and XLSX inventory export
- Google Sheets sync via optional n8n webhook (inbound + outbound)
- Edit bin metadata (zone, room, shelf, container description)
- `PATCH /update-bin` and `POST /api/move-items` API endpoints
- Environment-variable configuration (`BASE_URL`, `N8N_WEBHOOK_URL`, `DB_PATH`, `PHOTOS_DIR`, `APP_TITLE`)
- MIT License, `.env.example`, `.dockerignore`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`

[Unreleased]: https://github.com/nomi25home/kapaat/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/nomi25home/kapaat/compare/v1.2.0...v1.2.1
[0.1.0]: https://github.com/nomi25home/kapaat/releases/tag/v0.1.0
