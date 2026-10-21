# nomi25home Storage

Garage bin inventory app — track what's in every storage box, where it lives, and find it fast.

**Stack:** FastAPI · SQLite · Docker · single-page Jinja2 UI  
**Deployed at:** `https://bins.home.mihirfamily.com` (Authentik `admins` group, Dockge stack `garage-storage` on `.45:8099`)

---

## Features

- **Multi-level location hierarchy** — Zone → Room → Shelf → Bin; filter chips for each level (multi-select)
- **Items table** — photo thumbnail, name/category, qty, box, location + tags inline
- **Tags** — preset (christmas, summer, halloween, diwali) + custom; per-tag color coding; filter by tag
- **Bulk operations** — select items across bins; bulk add/remove tags; bulk move to another bin
- **Inline item editing** — name, category, quantity, tags; edit without leaving the drawer
- **Move items** — move one or many items to a different bin via a modal picker
- **Bin editing** — edit zone, room, shelf, container description on any bin
- **Photos** — per-item and per-bin photos; tap thumbnail to zoom; camera button to upload
- **QR labels** — per-bin QR code links to a mobile-optimized scan view; print label button
- **Search** — full-text across name, category, box ID, and tags
- **Export** — download full inventory as CSV or XLSX
- **Google Sheets sync** — n8n webhook pushes new items to a shared sheet; sheet→app sync via polling workflow

---

## Local development

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8096
# open http://localhost:8096
```

Data is stored in `/data/garage_inventory.db` and `/data/photos/`. For local dev these land in your working directory unless you override `DB_NAME` / `PHOTOS_DIR`.

---

## Deploy (homelab)

The app runs as a Docker container managed by Dockge on `192.168.74.45`.

**First deploy / after template changes** (templates are baked into the image):

```bash
# From your Mac — copy changed files then rebuild
scp templates/index.html app.py root@192.168.74.45:/opt/stacks/garage-storage/
ssh root@192.168.74.45 "cd /opt/stacks/garage-storage && docker compose build --no-cache && docker compose up -d"
```

**Config-only changes** (docker-compose.yml env vars, ports, volumes):

```bash
ssh root@192.168.74.45 "cd /opt/stacks/garage-storage && docker compose up -d"
```

Persistent data lives in the `garage_data` Docker volume — it survives rebuilds and redeployments.

---

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `TZ` | `America/New_York` | Timestamp timezone |
| `PYTHONUNBUFFERED` | `1` | Flush logs immediately |

`BASE_URL` and `N8N_WEBHOOK_URL` are hardcoded in `app.py` — update them if the domain or n8n host changes.

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Main dashboard |
| `GET` | `/bin/{bin_id}` | Mobile QR scan view for a single bin |
| `GET` | `/api/bins` | All bins (JSON) |
| `GET` | `/api/items?search=` | All items, optional full-text search |
| `POST` | `/add-bin` | Register a new bin |
| `PATCH` | `/update-bin/{bin_id}` | Edit bin zone/room/shelf/color |
| `DELETE` | `/delete-bin/{bin_id}` | Delete empty bin |
| `POST` | `/add-item` | Add item to a bin |
| `PATCH` | `/update-item/{item_id}` | Edit item name/category/qty/tags |
| `DELETE` | `/delete-item/{item_id}` | Delete item |
| `POST` | `/api/move-items` | Move items to a different bin |
| `POST` | `/api/bulk-tag` | Add or remove tags across multiple items |
| `GET` | `/api/tag-colors` | Get custom tag color mappings |
| `POST` | `/api/tag-colors` | Set a tag's color |
| `POST` | `/upload-photo/{type}/{id}` | Upload photo for item or bin |
| `GET` | `/photos/{filename}` | Serve a stored photo |
| `POST` | `/api/sync-row` | Ingest a row from Google Sheets (n8n) |
| `GET` | `/export/{csv\|xlsx}` | Download full inventory |

---

## Database schema

```sql
bins   (bin_id PK, zone, room, shelf_number, color_code, bin_photo)
items  (item_id PK, bin_id FK, name, category, quantity, tags, item_photo)
tag_colors (tag_name PK, hex)
```

`room` and `tags` were added via `ALTER TABLE` migrations — existing rows get empty strings.
