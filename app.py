import os
import sqlite3
import time
import urllib.parse
from pathlib import Path
import requests
from fastapi import FastAPI, Request, Form, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import pandas as pd

app = FastAPI(title="nomi25home Storage")
templates = Jinja2Templates(directory="templates")
DB_NAME = "/data/garage_inventory.db"
PHOTOS_DIR = Path("/data/photos")

# ⚠️ UPDATE to your local PC/server IP (e.g., http://192.168.74.45:8096)
# so mobile phone cameras can resolve QR codes over your home Wi-Fi.
BASE_URL = "https://bins.home.mihirfamily.com"

# Target n8n Webhook Node URL
N8N_WEBHOOK_URL = "https://n8n.home.mihirfamily.com/webhook/garage-update"


def init_db():
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bins (
            bin_id TEXT PRIMARY KEY,
            zone TEXT NOT NULL,
            shelf_number TEXT,
            color_code TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id TEXT,
            name TEXT NOT NULL,
            category TEXT,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY (bin_id) REFERENCES bins (bin_id)
        )
    ''')
    conn.commit()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tag_colors (
            tag_name TEXT PRIMARY KEY,
            hex TEXT NOT NULL
        )
    ''')
    conn.commit()
    for stmt in [
        "ALTER TABLE items ADD COLUMN item_photo TEXT",
        "ALTER TABLE bins ADD COLUMN bin_photo TEXT",
        "ALTER TABLE items ADD COLUMN tags TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError:
            pass
    conn.close()


init_db()


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def trigger_n8n_sync(bin_id: str, name: str, category: str, quantity: int, item_id: int = None):
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
        "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(bin_url, safe='')}",
    }
    try:
        response = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5, verify=False)
        print(f"n8n Sync Status: {response.status_code}")
    except Exception as e:
        print(f"Could not forward data to n8n webhook: {e}")


@app.post("/api/bulk-tag")
async def bulk_tag(request: Request):
    data = await request.json()
    item_ids = [int(i) for i in data.get("item_ids", []) if str(i).isdigit()]
    tags = [t.strip().lower() for t in data.get("tags", []) if t.strip()]
    if not item_ids or not tags:
        return JSONResponse({"error": "item_ids and tags required"}, status_code=400)
    mode = data.get("mode", "add")
    conn = get_db()
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
        b["qr_url"] = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(deep_link, safe='')}"
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
        cursor.execute(
            """
            SELECT items.*, bins.zone, bins.shelf_number, bins.color_code
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            ORDER BY items.bin_id, items.name
            """
        )
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, search: str = ""):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bins")
    bins = [dict(row) for row in cursor.fetchall()]

    for b in bins:
        deep_link = f"{BASE_URL}/bin/{urllib.parse.quote(b['bin_id'])}"
        b["qr_url"] = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(deep_link, safe='')}"

    if search:
        cursor.execute(
            '''
            SELECT items.*, bins.zone, bins.shelf_number
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            WHERE items.name LIKE ? OR items.category LIKE ?
            ''',
            (f"%{search}%", f"%{search}%"),
        )
    else:
        cursor.execute(
            '''
            SELECT items.*, bins.zone, bins.shelf_number
            FROM items JOIN bins ON items.bin_id = bins.bin_id
            '''
        )
    items = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "bins": bins, "items": items, "search": search, "single_bin": None},
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
        {"request": request, "bins": [], "items": items, "search": "", "single_bin": target_bin},
    )


@app.post("/add-bin")
async def web_add_bin(
    bin_id: str = Form(...),
    zone: str = Form(...),
    shelf: str = Form(...),
    color: str = Form(...),
):
    conn = get_db()
    try:
        conn.execute("INSERT INTO bins (bin_id, zone, shelf_number, color_code) VALUES (?, ?, ?, ?)", (bin_id, zone, shelf, color))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": f"Box ID '{bin_id}' already exists"}, status_code=400)
    finally:
        conn.close()
    return JSONResponse({"ok": True, "bin_id": bin_id})


@app.post("/add-item")
async def web_add_item(
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
    conn.close()
    background_tasks.add_task(trigger_n8n_sync, bin_id, name, category, qty, item_id)
    return JSONResponse({"ok": True, "item_id": item_id})


@app.delete("/delete-bin/{bin_id}")
async def delete_bin(bin_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as c FROM items WHERE bin_id = ?", (bin_id,))
    if cursor.fetchone()["c"] > 0:
        conn.close()
        return JSONResponse({"error": "Remove all items from this box before deleting it."}, status_code=400)
    cursor.execute("SELECT bin_photo FROM bins WHERE bin_id = ?", (bin_id,))
    row = cursor.fetchone()
    if row and row["bin_photo"]:
        p = PHOTOS_DIR / row["bin_photo"]
        if p.exists():
            p.unlink()
    conn.execute("DELETE FROM bins WHERE bin_id = ?", (bin_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


@app.patch("/update-item/{item_id}")
async def update_item(item_id: int, request: Request):
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
    conn = get_db()
    conn.execute(
        "UPDATE items SET name=?, category=?, quantity=?, tags=? WHERE item_id=?",
        (name, category, quantity, tags, item_id),
    )
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


@app.delete("/delete-item/{item_id}")
async def delete_item(item_id: int):
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
    conn.close()
    return JSONResponse({"ok": True})


@app.post("/upload-photo/{photo_type}/{record_id}")
async def upload_photo(photo_type: str, record_id: str, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
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
    filepath = PHOTOS_DIR / Path(filename).name
    if not filepath.exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    return FileResponse(str(filepath))


@app.post("/api/sync-row")
async def sync_row_from_sheet(request: Request):
    """Called by n8n to create items sourced from Google Sheets (no webhook fired to avoid loop)."""
    data = await request.json()
    bin_id = str(data.get("bin_id", "")).strip()
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "")).strip()
    try:
        quantity = int(float(str(data.get("quantity", 1))))
    except (ValueError, TypeError):
        quantity = 1
    zone = str(data.get("zone", "")).strip() or "Unknown"
    shelf = str(data.get("shelf", "")).strip() or "Unknown"

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

    cursor.execute(
        "INSERT INTO items (bin_id, name, category, quantity) VALUES (?, ?, ?, ?)",
        (bin_id, name, category, quantity),
    )
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"Sheet→App sync: '{name}' x{quantity} → {bin_id} (item_id={item_id})")
    return JSONResponse({"ok": True, "item_id": item_id})


@app.get("/export/{file_type}")
async def export_data(file_type: str):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        '''
        SELECT items.name, items.category, items.quantity,
               bins.bin_id, bins.zone, bins.shelf_number
        FROM items JOIN bins ON items.bin_id = bins.bin_id
        ''',
        conn,
    )
    conn.close()

    filepath = f"/tmp/garage_inventory.{'csv' if file_type == 'csv' else 'xlsx'}"
    if file_type == "csv":
        df.to_csv(filepath, index=False)
    else:
        df.to_excel(filepath, index=False)
    return FileResponse(filepath, filename=os.path.basename(filepath))
