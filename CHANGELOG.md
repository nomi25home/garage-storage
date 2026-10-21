# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

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

[Unreleased]: https://github.com/nomi25home/garage-storage/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nomi25home/garage-storage/releases/tag/v0.1.0
