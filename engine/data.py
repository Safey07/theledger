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

from .classify import clean_brand, clean_name

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
    """Return feed text from a URL or local path. Handles gzip feeds."""
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


SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD"}


def _money(value):
    """'12.99 GBP' / '£12.99' / '12.99' -> (12.99, 'GBP'), currency '' when the feed doesn't say."""
    text = str(value or "").strip()
    cur = next((code for sym, code in SYMBOLS.items() if sym in text), "")
    m = re.search(r"\b([A-Z]{3})\b", text.upper())
    if m:
        cur = m.group(1)
    num = re.search(r"\d[\d,]*(\.\d+)?", text)
    return (_num(num.group(0)) if num else None), cur


def _in_stock(value, default="1"):
    v = str(value if value is not None else default).strip().lower().replace("_", " ")
    return 0 if v in ("0", "false", "no", "n", "out of stock", "outofstock", "sold out", "preorder",
                      "pre-order", "backorder", "discontinued") else 1


def parse_awin(text, feed=None):
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
            "in_stock": _in_stock(row.get("in_stock")),
            "currency": (row.get("currency") or "").strip().upper(),
        }


def _google_rows(text):
    """Rows from a Google-style product feed: RSS/Atom XML with g: fields, or CSV/TSV."""
    if text.lstrip().startswith("<"):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text.strip())
        for item in root.iter():
            if item.tag.split("}")[-1] not in ("item", "entry"):
                continue
            row = {}
            for field in item:
                key = field.tag.split("}")[-1]
                if key == "link" and not (field.text or "").strip():
                    row.setdefault("link", field.get("href", ""))   # Atom puts the link in href
                else:
                    row.setdefault(key, (field.text or "").strip())
            yield row
        return
    first = text.split("\n", 1)[0]
    yield from csv.DictReader(io.StringIO(text), delimiter="\t" if first.count("\t") > first.count(",") else ",")


def parse_google(text, feed=None):
    """Google Merchant-style feeds (Rakuten Advertising and most networks): id, title, brand,
    price '12.99 GBP', sale_price, link, image_link, availability. One retailer per feed, so the
    retailer name comes from the feed's 'merchant' setting when the rows don't carry one."""
    feed = feed or {}
    for row in _google_rows(text):
        row = {k.strip().lower().replace("g:", ""): v for k, v in row.items() if k}
        regular, cur = _money(row.get("price"))
        sale, sale_cur = _money(row.get("sale_price"))
        price = sale if sale and (not regular or sale < regular) else regular
        if not price or not row.get("id"):
            continue
        yield {
            "id": f"{feed.get('name', 'feed')}-{row['id']}",
            "name": (row.get("title") or "").strip(),
            "brand": (row.get("brand") or "").strip(),
            "merchant": (row.get("merchant") or row.get("merchant_name") or feed.get("merchant") or "").strip(),
            "category": (row.get("product_type") or row.get("google_product_category") or "").strip(),
            "url": row.get("link") or "",
            "image": row.get("image_link") or "",
            "price": price,
            "rrp": regular if price != regular else None,
            "in_stock": _in_stock(row.get("availability"), "in stock"),
            "currency": (sale_cur if price == sale else cur) or feed.get("currency", ""),
        }


GENERIC_FIELDS = ("id", "name", "brand", "merchant", "category", "url", "image", "price", "rrp",
                  "in_stock", "currency")


def parse_generic_csv(text, feed=None):
    """Any CSV, mapped by 'columns' in config.yaml: {our_field: their_column}.
    Fields not mapped fall back to the feed's own setting (merchant, currency) or a blank."""
    feed = feed or {}
    cols = feed.get("columns") or {}
    for row in csv.DictReader(io.StringIO(text), delimiter=feed.get("delimiter", ",")):
        get = {f: (row.get(cols.get(f, f)) or "").strip() for f in GENERIC_FIELDS}
        price, cur = _money(get["price"])
        if not price or not get["id"]:
            continue
        yield {
            "id": f"{feed.get('name', 'feed')}-{get['id']}",
            "name": get["name"], "brand": get["brand"],
            "merchant": get["merchant"] or feed.get("merchant", ""),
            "category": get["category"], "url": get["url"], "image": get["image"],
            "price": price, "rrp": _money(get["rrp"])[0],
            "in_stock": _in_stock(get["in_stock"] or None),
            "currency": (get["currency"].upper() or cur or feed.get("currency", "")),
        }


# feeds[].format in config.yaml picks one of these. Switching network is a config change.
PARSERS = {"awin": parse_awin, "rakuten": parse_google, "google": parse_google,
           "generic_csv": parse_generic_csv}


def _words(words):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b") if words else None


def keep(product, filters):
    """Whole-word matching, so 'car' never removes 'Carolina Herrera'."""
    allow = {m.lower() for m in filters.get("merchants_allow", [])}
    if allow and product["merchant"].lower() not in allow:
        return False          # only retailers we've joined, so every link earns
    cur = filters.get("currency")
    if cur and product.get("currency") and product["currency"] != cur:
        return False          # never show euro prices as pounds
    if product["price"] < filters.get("min_price", 0):
        return False
    hay = f"{product['name']} {product['category']}".lower()
    ex, inc = _words(filters.get("exclude_keywords", [])), _words(filters.get("include_keywords", []))
    if ex and ex.search(hay):
        return False
    return bool(inc and inc.search(hay))


def _feed(source):
    """A feed is a config.yaml entry, or a bare path/URL (demo and tests), read as Awin."""
    return dict(source) if isinstance(source, dict) else {"url": source, "format": "awin"}


def feed_filters(feed, filters):
    """A feed's own merchants_allow (if it has one) replaces the global list for that feed."""
    return {**filters, "merchants_allow": feed["merchants_allow"]} if "merchants_allow" in feed else filters


def ingest(db, sources, filters, day, names=None):
    """Store today's price for every matching product. Returns count.
    names maps a feed's retailer spelling to the one shown on the site."""
    count = 0
    for feed in map(_feed, sources):
        url = _expand_env(feed.get("url") or "")
        if not url:             # optional extra feed not set up yet
            continue
        parse = PARSERS.get(feed.get("format", "awin"))
        if not parse:
            print(f"::warning::Feed {feed.get('name', '')}: unknown format '{feed.get('format')}', skipped")
            continue
        try:
            text = read_feed(url)
        except Exception as err:   # one broken retailer feed must not stop the others
            print(f"::warning::Feed {feed.get('name', '')} failed, skipping: {str(err).replace(url, '<feed url>')[:120]}")
            continue
        rules = feed_filters(feed, filters)
        for p in parse(text, feed):
            if not keep(p, rules):
                continue
            p["merchant"] = (names or {}).get(p["merchant"], p["merchant"])
            p["brand"] = clean_brand(p["brand"])
            p["name"] = clean_name(p["brand"], p["name"])
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


def allowed_merchants(cfg):
    """Every retailer name the config currently allows (lower case), or None when any is allowed."""
    lists = [cfg["filters"].get("merchants_allow") or []] + \
            [f["merchants_allow"] for f in cfg.get("feeds") or [] if "merchants_allow" in f]
    if not all(lists):
        return None
    names = {n for group in lists for n in group}
    shown = cfg.get("merchant_names") or {}
    return {n.lower() for n in names | {shown[n] for n in names if n in shown}}


def last_good_day(db, before, allow=None):
    """Most recent day before `before` with in-stock prices from a retailer we still use."""
    rows = db.execute(
        """SELECT DISTINCT pr.day, p.merchant FROM prices pr JOIN products p ON p.id=pr.product_id
           WHERE pr.day<? AND pr.in_stock=1 ORDER BY pr.day DESC""", (before,))
    for r in rows:
        if allow is None or r["merchant"].lower() in allow:
            return r["day"]
    return None


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
