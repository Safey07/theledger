"""Turn price data into a static site, an email digest and social posts."""
import json
import os
import shutil
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

from jinja2 import Environment, FileSystemLoader

import statistics

from .classify import base_key, match_key, tag, verdict
from .content import build_content, load_guides
from .data import allowed_merchants, history, slugify


def _match(c, preset):
    if "g" in preset and c["g"] != preset["g"]:
        return False
    if preset.get("k") and not c["k"]:
        return False
    if "max" in preset and c["p"] > preset["max"]:
        return False
    return True

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env():
    return Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")), autoescape=True)


def price_chart(points, sym):
    """Inline SVG line chart of a product's price history."""
    if len(points) < 2:
        return "<p class='shop'>Tracking started recently. History builds daily.</p>"
    w, h, pad = 520, 180, 28
    prices = [p for _, p in points]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    xs = [pad + i * (w - 2 * pad) / (len(points) - 1) for i in range(len(points))]
    ys = [h - pad - (p - lo) / span * (h - 2 * pad) for p in prices]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    area = f"{path} L{xs[-1]:.1f},{h - pad} L{xs[0]:.1f},{h - pad} Z"
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Price history chart" '
        f'style="max-width:{w}px;display:block">'
        f'<path d="{area}" fill="var(--gold)" opacity=".10"/>'
        f'<path d="{path}" fill="none" stroke="var(--gold)" stroke-width="2"/>'
        f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4" fill="var(--drop)"/>'
        f'<text x="{pad}" y="14" font-size="11" fill="var(--muted)">High {sym}{hi:.2f}</text>'
        f'<text x="{pad}" y="{h - 8}" font-size="11" fill="var(--muted)">Low {sym}{lo:.2f}</text>'
        f'<text x="{w - pad}" y="{h - 8}" font-size="11" fill="var(--muted)" text-anchor="end">'
        f'{points[0][0]} to {points[-1][0]}</text></svg>'
    )


def _write(path, html):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def _current_products(db, day, allow=None):
    rows = [dict(r) for r in db.execute(
        """SELECT p.*, pr.price FROM prices pr JOIN products p ON p.id=pr.product_id
           WHERE pr.day=? AND pr.in_stock=1""", (day,))]
    return [r for r in rows if allow is None or r["merchant"].lower() in allow]


COLLECTIONS = [
    # slug, heading, intro, preset filter for the browse page
    ("shop", "Shop every fragrance", "Every fragrance we track, at its cheapest UK price today.", {}),
    ("men", "Men's fragrance deals", "Men's aftershave and cologne at today's lowest UK prices.", {"g": "men"}),
    ("women", "Women's perfume deals", "Women's perfume at today's lowest UK prices.", {"g": "women"}),
    ("unisex", "Unisex fragrances", "Shared and gender-neutral scents at today's lowest UK prices.", {"g": "unisex"}),
    ("niche", "Niche fragrance deals", "Creed, Parfums de Marly, MFK, Xerjoff and more, at today's lowest UK prices.", {"k": 1}),
    ("under-50", "Fragrances under £50", "Designer and niche fragrances you can buy for under £50 today.", {"max": 50}),
    ("under-100", "Fragrances under £100", "Designer and niche fragrances you can buy for under £100 today.", {"max": 100}),
]


def _catalogue(products, sym):
    """One entry per fragrance (brand + name), using its cheapest retailer today."""
    groups = {}
    for p in products:
        groups.setdefault(match_key(p["brand"], p["name"]), []).append(p)
    items = []
    for listings in groups.values():
        best = min(listings, key=lambda x: x["price"])
        brand, name = best["brand"], min((x["name"] for x in listings), key=len)
        usual = best.get("usual")
        pct = round((usual - best["price"]) / usual * 100) if usual and usual > best["price"] else 0
        items.append({
            "b": brand, "n": name, "s": best["slug"], "p": round(best["price"], 2),
            "u": round(usual, 2) if pct >= 5 else None, "d": pct if pct >= 5 else 0,
            "g": best["gender"], "k": 1 if best["niche"] else 0, "r": len(listings),
            "m": best["merchant"], "i": best["image"] or "", "c": best["conc"], "h": best["shape"],
            "v": best["verdict"]["k"], "f": (best.get("notes") or {}).get("f", ""),
            "x": " ".join(w for k_ in ("t", "h", "b") for w in (best.get("notes") or {}).get(k_, [])).lower(),
        })
    items.sort(key=lambda x: (-x["d"], x["b"], x["n"]))
    return items


def build_site(db, cfg, day, drops, out_dir, demo=False, prices_from=None):
    """prices_from: show that earlier day's prices (labelled) because no feed worked today."""
    env = _env()
    site = cfg["site"]
    sym = site["currency_symbol"]
    niche_brands = [b.lower() for b in cfg.get("niche_brands", [])] or None
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    static = os.path.join(HERE, "static")   # verification files, favicon, etc.
    if os.path.isdir(static):
        shutil.copytree(static, out_dir)
    action = cfg.get("signup_action", "#")
    common = {"site": site, "updated": day, "demo": demo,
              "amazon_tag": (cfg.get("amazon") or {}).get("tag") or None,
              "signup_action": action if action and action != "#" else None,
              "collections": COLLECTIONS, "guides": load_guides(),
              "stale": date.fromisoformat(prices_from).strftime("%-d %B %Y") if prices_from else None,
              "checked": datetime.now(ZoneInfo("Europe/London")).strftime("%-d %B %Y, %H:%M")}
    updated, day = day, prices_from or day   # from here on, day is the day whose prices we show
    for d in drops:
        tag(d, niche_brands)

    # Items announced in the last 7 days that are still at or below that price
    week_ago = (date.fromisoformat(day) - timedelta(days=7)).isoformat()
    drop_ids = {d["id"] for d in drops}
    recent = []
    for r in [] if prices_from else db.execute(
            """SELECT pub.product_id, MIN(pub.price) AS announced, p.*, pr.price
               FROM published pub JOIN products p ON p.id=pub.product_id
               JOIN prices pr ON pr.product_id=pub.product_id AND pr.day=?
               WHERE pub.day>=? AND pub.day<? GROUP BY pub.product_id""", (day, week_ago, day)):
        if r["id"] not in drop_ids and r["price"] <= r["announced"]:
            recent.append(tag({**dict(r), "was": None}, niche_brands))

    products = _current_products(db, day, allowed_merchants(cfg) if prices_from else None)
    by_name = {}
    for p in products:
        tag(p, niche_brands)
        by_name.setdefault(match_key(p["brand"], p["name"]), []).append(p)

    # Price history for every listing (used by product pages and the catalogue)
    month_ago = (date.fromisoformat(day) - timedelta(days=30)).isoformat()
    for p in products:
        pts = history(db, p["id"], 90)
        p["pts"] = pts
        month = [pr for d_, pr in pts if d_ >= month_ago]
        past = [pr for d_, pr in pts if month_ago <= d_ < day]
        p["low_30"] = min(month) if month else None
        p["usual"] = statistics.median(past) if past else None

    notes_path = os.path.join(HERE, "content", "notes.yaml")
    notes = {}
    if os.path.exists(notes_path):
        import yaml
        with open(notes_path, encoding="utf-8") as fh:
            notes = yaml.safe_load(fh) or {}
    for p in products:
        p["notes"] = notes.get(base_key(p["brand"], p["name"]))
        p["verdict"] = verdict(p["price"], p["pts"], day)

    catalogue = _catalogue(products, sym)
    _write(os.path.join(out_dir, "catalog.json"), json.dumps(catalogue, separators=(",", ":")))
    counts = {"all": len(catalogue), "brands": len({c["b"] for c in catalogue}),
              "retailers": len({p["merchant"] for p in products})}

    today_label = date.fromisoformat(updated).strftime("%A %-d %B %Y")
    drop_brands = sorted({d["brand"] for d in drops})
    _write(os.path.join(out_dir, "index.html"), env.get_template("index.html").render(
        **common, root="", drops=drops, recent=recent[:12], today_label=today_label,
        counts=counts, drop_brands=drop_brands, top=catalogue[:8], site_jsonld=_site_jsonld(site)))
    # GitHub Pages serves this for any missing URL, at any depth, so links are root-relative
    _write(os.path.join(out_dir, "404.html"), env.get_template("404.html").render(
        **common, root="/", noindex=True, nocanon=True))

    # Browse pages: shop all plus collections. First 24 rendered for search engines, the rest load from JSON.
    # Empty ones still exist (nav links to them) but stay out of search engines until they have prices.
    brand_list = sorted({c["b"] for c in catalogue})
    listed = []
    for slug, heading, intro, preset in COLLECTIONS:
        first = [c for c in catalogue if _match(c, preset)]
        if first:
            listed.append(f"{slug}.html")
        _write(os.path.join(out_dir, f"{slug}.html"), env.get_template("browse.html").render(
            **common, root="", heading=heading, intro=intro, canon=f"{slug}.html", slug=slug,
            preset=json.dumps(preset), first=first[:24], total=len(first), brand_list=brand_list,
            noindex=not first))

    # One SEO page per product listing
    for p in products:
        p["chart"] = price_chart(p["pts"], sym)
        p["brand_slug"] = slugify(p["brand"])
        compare = sorted(by_name[match_key(p["brand"], p["name"])], key=lambda o: o["price"])
        p["jsonld"] = _product_jsonld(p, compare, common["stale"], site["base_url"])
        more = [c for c in catalogue if c["b"] == p["brand"] and c["n"] != p["name"]][:4]
        _write(os.path.join(out_dir, "p", f"{p['slug']}.html"),
               env.get_template("product.html").render(**common, root="../", p=p, compare=compare,
                                                        cheapest=compare[0], more=more))

    # Brand pages and brand index
    brands = {}
    for c in catalogue:
        brands.setdefault(c["b"], []).append(c)
    for brand, items in brands.items():
        items = sorted(items, key=lambda x: x["p"])
        _write(os.path.join(out_dir, "b", f"{slugify(brand)}.html"), env.get_template("listing.html").render(
            **common, root="../", heading=f"{brand} fragrance prices",
            intro=f"Today's cheapest UK prices for {len(items)} {brand} fragrances, lowest first.",
            canon=f"b/{slugify(brand)}.html", items=items, links=[]))
    links = [{"href": f"b/{slugify(b)}.html", "label": b, "note": f"{len(v)}"}
             for b, v in sorted(brands.items())]
    _write(os.path.join(out_dir, "brands.html"), env.get_template("listing.html").render(
        **common, root="", heading="All brands", canon="brands.html",
        intro="Every fragrance brand we track, with today's prices.", items=[], links=links,
        noindex=not links))
    if links:
        listed.append("brands.html")

    # Trust pages and guides
    content_urls = build_content(env, common, cfg, out_dir, _write)

    # Sitemap and robots for search engines
    base = site["base_url"].rstrip("/")
    urls = [""] + listed + content_urls + \
           [f"b/{slugify(b)}.html" for b in brands] + \
           [f"p/{p['slug']}.html" for p in products]
    sitemap = "".join(f"<url><loc>{escape(base)}/{u}</loc><lastmod>{updated}</lastmod></url>" for u in urls)
    _write(os.path.join(out_dir, "sitemap.xml"),
           f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sitemap}</urlset>')
    _write(os.path.join(out_dir, "robots.txt"), f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    return len(urls)


def build_digest(cfg, day, drops, out_path):
    """Email-safe HTML (inline styles, tables) for the morning digest."""
    site = cfg["site"]
    sym = site["currency_symbol"]
    items = drops[: cfg["detection"]["max_digest_items"]]
    base = site["base_url"].rstrip("/")
    rows = "".join(
        f'<tr><td style="padding:14px 0;border-bottom:1px solid #e4dccf">'
        f'<div style="font:11px Arial;letter-spacing:2px;text-transform:uppercase;color:#7a7066">{escape(d["brand"])}</div>'
        f'<div style="font:16px Georgia;color:#1d1a16;margin:3px 0">{escape(d["name"])}</div>'
        f'<div style="font:14px Arial;color:#1d1a16"><b>{sym}{d["price"]:.2f}</b> '
        f'<span style="color:#7a7066;text-decoration:line-through">{sym}{d["was"]:.2f}</span> '
        f'<span style="color:#a3362b;font-weight:bold">−{d["pct"]}%</span> at {escape(d["merchant"])}</div>'
        f'<a href="{base}/p/{d["slug"]}.html" style="font:13px Arial;color:#9c7a3c">See the deal</a></td></tr>'
        for d in items)
    subject = (f"{len(drops)} fragrance drops today: {items[0]['brand']} −{items[0]['pct']}%"
               if items else "No big fragrance drops today")
    html = (f'<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;background:#fffdf9">'
            f'<tr><td style="font:28px Georgia;color:#1d1a16;padding:20px 0 4px">{escape(site["name"])}</td></tr>'
            f'<tr><td style="font:13px Arial;color:#7a7066;padding-bottom:10px">{day}</td></tr>{rows}'
            f'<tr><td style="font:11px Arial;color:#7a7066;padding:18px 0">Prices change quickly. '
            f'We earn a commission on purchases made through our links.</td></tr></table>')
    _write(out_path, html)
    return subject, html


def build_social(cfg, day, drops, out_dir):
    """Portrait image cards plus captions, ready for TikTok/Instagram scheduling tools."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(out_dir, exist_ok=True)
    sym = cfg["site"]["currency_symbol"]
    serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
    sans = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    sans_b = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            return ImageFont.load_default()

    def wrap(text, f, width, draw):
        words, lines, cur = text.split(), [], ""
        for w in words:
            test = f"{cur} {w}".strip()
            if draw.textlength(test, font=f) <= width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        return lines + [cur]

    captions = []
    for i, d in enumerate(drops[: cfg["detection"]["max_social_cards"]], 1):
        img = Image.new("RGB", (1080, 1350), "#f6f2ec")
        dr = ImageDraw.Draw(img)
        dr.rectangle([60, 60, 1020, 1290], outline="#9c7a3c", width=3)
        dr.text((540, 170), cfg["site"]["name"].upper(), font=font(sans_b, 34), fill="#9c7a3c", anchor="mm")
        dr.text((540, 300), "PRICE DROP", font=font(sans, 30), fill="#7a7066", anchor="mm")
        dr.text((540, 470), f"−{d['pct']}%", font=font(serif, 220), fill="#a3362b", anchor="mm")
        dr.text((540, 640), d["brand"].upper(), font=font(sans_b, 40), fill="#1d1a16", anchor="mm")
        y = 710
        for line in wrap(d["name"], font(serif, 52), 860, dr)[:3]:
            dr.text((540, y), line, font=font(serif, 52), fill="#1d1a16", anchor="mm")
            y += 70
        dr.text((540, y + 90), f"{sym}{d['price']:.2f}", font=font(sans_b, 96), fill="#1d1a16", anchor="mm")
        dr.text((540, y + 180), f"usually {sym}{d['was']:.2f}  ·  {d['merchant']}", font=font(sans, 34),
                fill="#7a7066", anchor="mm")
        if d.get("all_time_low"):
            dr.text((540, 1200), "LOWEST PRICE WE'VE TRACKED", font=font(sans_b, 30), fill="#2f6b4f", anchor="mm")
        img.save(os.path.join(out_dir, f"card_{i}.png"))
        captions.append(
            f"card_{i}.png\n{d['brand']} {d['name']} is down {d['pct']}% to {sym}{d['price']:.2f} "
            f"at {d['merchant']} (usually {sym}{d['was']:.2f}). Link in bio for today's full list.\n"
            f"#fragrance #perfume #{slugify(d['brand']).replace('-', '')} #fragrancedeals #ukdeals #ad\n")
    _write(os.path.join(out_dir, "captions.txt"), "\n".join(captions))
    return len(captions)


def _site_jsonld(site):
    """Organization and WebSite (with site search) for the homepage."""
    base = site["base_url"].rstrip("/")
    same = [u for u in (
        site.get("instagram") and f"https://www.instagram.com/{site['instagram']}/",
        site.get("tiktok") and f"https://www.tiktok.com/@{site['tiktok']}",
        site.get("facebook") and f"https://www.facebook.com/{site['facebook']}") if u]
    org = {"@type": "Organization", "@id": f"{base}/#org", "name": site["name"], "url": f"{base}/",
           "logo": f"{base}/logo.png", "description": site["tagline"]}
    if site.get("contact_email"):
        org["email"] = site["contact_email"]
    if same:
        org["sameAs"] = same
    web = {"@type": "WebSite", "@id": f"{base}/#website", "name": site["name"], "url": f"{base}/",
           "inLanguage": "en-GB", "publisher": {"@id": f"{base}/#org"},
           "potentialAction": {"@type": "SearchAction",
                               "target": {"@type": "EntryPoint", "urlTemplate": f"{base}/shop.html?q={{search_term_string}}"},
                               "query-input": "required name=search_term_string"}}
    return json.dumps({"@context": "https://schema.org", "@graph": [org, web]}).replace("</", "<\\/")


def _product_jsonld(p, compare, stale=None, base_url=""):
    """Price-comparison markup. We list other shops' prices, so this is an AggregateOffer
    (Google product snippet), not a merchant listing that needs shipping and returns data.
    Empty fields are left out rather than sent as null."""
    title = f"{p['brand']} {p['name']}".strip()
    low, high = compare[0]["price"], compare[-1]["price"]
    shops = len({c["merchant"] for c in compare})
    data = {
        "@context": "https://schema.org", "@type": "Product", "name": title,
        "url": f"{base_url.rstrip('/')}/p/{p['slug']}.html",
        "description": (f"Compare UK prices for {title}. Lowest {f'on {stale}' if stale else 'today'} £{low:.2f} at {compare[0]['merchant']}"
                        f"{f', across {shops} retailers' if shops > 1 else ''}."),
        "offers": {"@type": "AggregateOffer", "priceCurrency": "GBP",
                   "lowPrice": f"{low:.2f}", "highPrice": f"{high:.2f}", "offerCount": len(compare)},
    }
    if p.get("brand"):
        data["brand"] = {"@type": "Brand", "name": p["brand"]}
    image = p.get("image") or next((c.get("image") for c in compare if c.get("image")), None)
    if image:
        data["image"] = image
    return json.dumps(data).replace("</", "<\\/")
