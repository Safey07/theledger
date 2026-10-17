"""Feed ingest, price history storage and drop detection."""
import csv
import io
import os
import re
import sqlite3
import statistics
import urllib.request
import gzip
from datetime import date, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT, brand TEXT, merchant TEXT, category TEXT,
    url TEXT, image TEXT, slug TEXT, first_seen TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    product_id TEXT, day TEXT, price REAL, rrp REAL, in_stock INTEGER,
    PRIMARY KEY (product_id, day)
);
CREATE TABLE IF NOT EXISTS published (
    product_id TEXT, day TEXT, price REAL,
    PRIMARY KEY (product_id, day)
);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:90]


def _expand_env(value):
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)


def read_feed(source):
    """Return CSV text from a URL or local path. Handles gzip feeds."""
    if source.startswith("http"):
        with urllib.request.urlopen(source, timeout=120) as resp:
            raw = resp.read()
    else:
        with open(source, "rb") as fh:
            raw = fh.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def _num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_awin(text):
    """Map Awin product-feed columns onto our product shape."""
    for row in csv.DictReader(io.StringIO(text)):
        price = _num(row.get("search_price"))
        if not price:
            continue
        yield {
            "id": f"{row.get('merchant_id', 'm')}-{row.get('aw_product_id') or row.get('merchant_product_id')}",
            "name": (row.get("product_name") or "").strip(),
            "brand": (row.get("brand_name") or "").strip(),
            "merchant": (row.get("merchant_name") or "").strip(),
            "category": (row.get("category_name") or row.get("merchant_category") or "").strip(),
            "url": row.get("aw_deep_link") or row.get("merchant_deep_link") or "",
            "image": row.get("merchant_image_url") or row.get("aw_image_url") or "",
            "price": price,
            "rrp": _num(row.get("rrp_price")),
            "in_stock": 0 if str(row.get("in_stock", "1")).strip() in ("0", "false", "no") else 1,
        }


def keep(product, filters):
    hay = f"{product['name']} {product['category']}".lower()
    if any(word in hay for word in filters.get("exclude_keywords", [])):
        return False
    return any(word in hay for word in filters.get("include_keywords", []))


def ingest(db, sources, filters, day):
    """Store today's price for every matching product. Returns count."""
    count = 0
    for source in sources:
        text = read_feed(_expand_env(source))
        for p in parse_awin(text):
            if not keep(p, filters):
                continue
            db.execute(
                """INSERT INTO products (id,name,brand,merchant,category,url,image,slug,first_seen)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, url=excluded.url,
                   image=excluded.image, merchant=excluded.merchant""",
                (p["id"], p["name"], p["brand"], p["merchant"], p["category"], p["url"],
                 p["image"], slugify(f"{p['brand']} {p['name']} {p['merchant']}"), day),
            )
            db.execute(
                "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?)",
                (p["id"], day, p["price"], p["rrp"], p["in_stock"]),
            )
            count += 1
    db.commit()
    return count


def history(db, product_id, days=90):
    rows = db.execute(
        "SELECT day, price FROM prices WHERE product_id=? ORDER BY day DESC LIMIT ?",
        (product_id, days),
    ).fetchall()
    return list(reversed([(r["day"], r["price"]) for r in rows]))


def detect_drops(db, day, rules):
    """Find in-stock items priced well below their own recent median."""
    start = (date.fromisoformat(day) - timedelta(days=rules["history_days"])).isoformat()
    today = db.execute(
        """SELECT p.*, pr.price, pr.rrp FROM prices pr JOIN products p ON p.id=pr.product_id
           WHERE pr.day=? AND pr.in_stock=1""", (day,)
    ).fetchall()
    drops = []
    for item in today:
        past = [r["price"] for r in db.execute(
            "SELECT price FROM prices WHERE product_id=? AND day>=? AND day<?",
            (item["id"], start, day))]
        if not past:
            continue
        median = statistics.median(past)
        saving = median - item["price"]
        pct = saving / median * 100 if median else 0
        if pct < rules["min_drop_pct"] or saving < rules["min_drop_abs"]:
            continue
        already = db.execute(
            "SELECT 1 FROM published WHERE product_id=? AND price<=? AND day>=?",
            (item["id"], item["price"], start)).fetchone()
        if already:
            continue  # same or lower price already announced this month
        all_time_low = item["price"] <= min(past)
        drops.append({**dict(item), "was": round(median, 2), "saving": round(saving, 2),
                      "pct": round(pct), "all_time_low": all_time_low})
    # Rank: biggest percentage first, all-time lows break ties
    drops.sort(key=lambda d: (d["pct"], d["all_time_low"], d["saving"]), reverse=True)
    return drops


def mark_published(db, drops, day):
    db.executemany("INSERT OR REPLACE INTO published VALUES (?,?,?)",
                   [(d["id"], day, d["price"]) for d in drops])
    db.commit()
