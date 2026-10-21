# Kapaat

> **Kapaat** (Punjabi: ਕਪਾਟ — *cabinet, storage compartment*) is a self-hosted storage inventory app that tracks what's inside every physical storage box, where each box lives, and surfaces it through a fast single-page web UI.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688)](https://fastapi.tiangolo.com/)

---

## Core Features

| Feature | Description |
|---|---|
| **Location hierarchy** | Room → Zone → Shelf → Bin — multi-select filter chips for each level |
| **Items table** | Photo thumbnail, name, category, qty, location, and tags in one view |
| **Inline editing** | Edit any item's name, category, quantity, and tags without leaving the page |
| **Move items** | Move one or many items to a different bin via a modal picker |
| **Bulk operations** | Select across bins — bulk add/remove tags, bulk move |
| **Tags** | Preset seasonal tags + custom tags; per-tag color coding; tag filter |
| **Photos** | Per-item and per-bin photo upload; tap thumbnail to zoom |
| **QR labels** | Auto-generated QR per bin — scan on mobile to see contents; print label |
| **Search** | Full-text across name, category, box ID, and tags |
| **Export** | Download full inventory as CSV or XLSX |
| **Sheets sync** | Optional n8n webhook integration for Google Sheets bidirectional sync |

---

## Quick Start (local)

**Requirements:** Python 3.11+, pip

```bash
git clone https://github.com/nomi25home/kapaat.git
cd kapaat

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set BASE_URL to http://localhost:8096 at minimum

uvicorn app:app --reload --port 8096
```

Open [http://localhost:8096](http://localhost:8096). The SQLite database and photo store are created automatically on first run at the paths defined in `.env`.

---

## Docker (production)

### Minimal `docker-compose.yml`

```yaml
services:
  kapaat:
    image: ghcr.io/nomi25home/kapaat:1   # or build: .
    restart: unless-stopped
    ports:
      - "8096:8096"
    volumes:
      - kapaat_data:/data
    environment:
      - BASE_URL=https://storage.yourdomain.com
      - N8N_WEBHOOK_URL=                              # leave blank to disable
      - TZ=America/New_York

volumes:
  kapaat_data:
```

### Building from source

```bash
docker build -t kapaat .
docker run -d -p 8096:8096 \
  -v kapaat_data:/data \
  -e BASE_URL=http://192.168.1.10:8096 \
  kapaat
```

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and fill in your values.

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://localhost:8096` | Public URL used to build QR code deep-links. Must be reachable from phones on your network. |
| `N8N_WEBHOOK_URL` | *(empty — disabled)* | n8n webhook for Google Sheets sync. Leave blank to disable. |
| `DB_PATH` | `/data/garage_inventory.db` | SQLite database path inside the container. |
| `PHOTOS_DIR` | `/data/photos` | Photo storage directory inside the container. |
| `APP_TITLE` | `Kapaat` | Browser tab title and API docs title. |
| `LOCALE` | `en` | UI language code — must match a file in `locales/` (e.g. `en`). |
| `TZ` | `America/New_York` | Timezone for timestamps. |
| `DB_ENCRYPTION_KEY` | *(empty — disabled)* | Optional passphrase for AES-256 on-disk encryption via SQLCipher. Requires `ENABLE_SQLCIPHER=1` build arg. **If you lose this key, your data is unrecoverable.** |

> **Tip — QR scanning away from home:** `BASE_URL` must match what your phone can reach. On a local network, use your server's LAN IP (e.g. `http://192.168.1.10:8096`). For off-site scanning, set `BASE_URL` to your [Tailscale](https://tailscale.com/) IP or a zero-trust tunnel hostname — the QR deep-links will resolve wherever the phone has a Tailscale connection, making garage scans work even from a friend's WiFi.

---

## Data Portability & Migration FAQ

**Where is my data stored?**  
Everything lives in a single SQLite file (`garage_inventory.db`) and a flat photo directory (`photos/`). Both are inside the Docker volume mapped to `/data`.

**How do I back up my data?**  
The easiest way is the **Download full backup** button in the navbar (the `backup` icon). It streams a `.zip` containing a live DB snapshot and all photos directly to your browser — no shell required.

For automated or scheduled backups, use the shell approach:
```bash
docker run --rm -v kapaat_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/kapaat-backup-$(date +%F).tar.gz /data
```

Or hit the API directly:
```bash
curl -o kapaat-backup.zip https://bins.yourdomain.com/api/backup/download
```

**How do I move to a new host?**  
Copy the backup archive to the new host, extract it into a Docker volume, and start the container pointing at that volume. No migrations needed — the app runs `ALTER TABLE` migrations on startup automatically.

**Can I use a different database?**  
Not currently — SQLite is intentional to keep the deployment footprint to a single file. Contributions adding a Postgres adapter are welcome.

**How do I reset everything?**  
Delete (or rename) the Docker volume: `docker volume rm kapaat_data`.

---

## Architecture

```
browser  ──HTTP──▶  FastAPI (app.py)
                        │
                   Jinja2 template (templates/index.html)
                   Single-page, vanilla JS, no build step
                        │
              ┌─────────┴──────────┐
         SQLite DB            /data/photos/
       (garage_inventory.db)   (flat file store)
                        │
                  optional n8n webhook
                  (Google Sheets sync)
```

- **Backend:** FastAPI + uvicorn; pure Python stdlib + SQLite for zero-dependency data layer.
- **Frontend:** Single Jinja2 template rendered server-side on first load; all subsequent interactions are fetch-based JSON API calls. No JavaScript framework, no build step.
- **Storage:** SQLite for structured data, flat files for photos. Both live in one Docker volume for trivial backup and portability.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Main dashboard |
| `GET` | `/bin/{bin_id}` | Mobile QR scan view |
| `GET` | `/api/bins` | All bins (JSON) |
| `GET` | `/api/items?search=` | All items, optional full-text search |
| `POST` | `/add-bin` | Register a new bin |
| `PATCH` | `/update-bin/{bin_id}` | Edit bin zone / room / shelf / container |
| `DELETE` | `/delete-bin/{bin_id}` | Delete an empty bin |
| `POST` | `/add-item` | Add item to a bin |
| `PATCH` | `/update-item/{item_id}` | Edit item fields |
| `DELETE` | `/delete-item/{item_id}` | Delete item |
| `POST` | `/api/move-items` | Move items to a different bin |
| `POST` | `/api/bulk-tag` | Add or remove tags across many items |
| `GET` | `/api/tag-colors` | Get custom tag color mappings |
| `POST` | `/api/tag-colors` | Set a tag's hex color |
| `POST` | `/upload-photo/{type}/{id}` | Upload photo (type: `item` or `bin`) |
| `GET` | `/photos/{filename}` | Serve a stored photo |
| `POST` | `/api/sync-row` | Ingest a row from Google Sheets (n8n) |
| `GET` | `/export/{csv\|xlsx}` | Download full inventory |
| `GET` | `/api/backup` | Download a point-in-time SQLite snapshot (`.db`) |
| `GET` | `/api/backup/download` | Download a full backup archive (DB + photos as `.zip`) |

### Google Sheets sync — conflict strategy

`/api/sync-row` is a **Sheet → App** write path only. It creates a new item when the row has no `Item ID`; it does not update existing items.

**What happens on a simultaneous edit?**

| Scenario | Outcome |
|---|---|
| Item edited in Kapaat while the same row is unchanged in Sheets | Safe — Sheets later syncs the original values on next n8n run; they do not overwrite the Kapaat edit because `sync-row` only inserts rows with no `Item ID`. |
| Item name changed in both Kapaat and Sheets before next n8n run | Kapaat wins — the Sheets row already has an `Item ID`, so `sync-row` skips it. The mismatch is visible in Sheets. |
| Item deleted in Kapaat; row still in Sheets | The row's `Item ID` is orphaned in Sheets. A subsequent n8n run sees the `Item ID` present and skips re-insertion. Clean up the Sheets row manually or via a cleanup workflow. |

The sync is intentionally append-only to prevent silent overwrites of locally edited data.

---

## Database Schema

```sql
bins       (bin_id PK, room, zone, shelf_number, color_code, bin_photo)
items      (item_id PK, bin_id FK, name, category, quantity, tags, item_photo)
tag_colors (tag_name PK, hex)
```

`room` and `tags` were added via `ALTER TABLE` migrations — the app handles these automatically on startup, so existing databases are safe to upgrade in-place.

---

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md). Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.

## Security

See [SECURITY.md](.github/SECURITY.md) for the responsible disclosure policy.

## License

[MIT](LICENSE) © 2025 nomi25home
