"""Render vertical Reels (1080x1920, 30fps) for the day's top drops.

Each frame is drawn by a headless browser from engine/reel.html, using the
real price data, then encoded with ffmpeg. No stock footage or AI imagery.
"""
import base64
import io
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import urllib.request

from .data import history

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(HERE, ".cache", "fonts")
FONTS = {
    "Cormorant.ttf": "ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf",
    "CormorantItalic.ttf": "ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf",
    "Inter.ttf": "ofl/inter/Inter%5Bopsz,wght%5D.ttf",
}
FPS = 30
DURATION = 9.6
CONCENTRATIONS = ["eau de parfum", "eau de toilette", "eau de cologne", "extrait de parfum",
                  "parfum", "elixir", "intense", "cologne", "edp", "edt"]


def ensure_fonts():
    """Open-licence fonts from Google Fonts' GitHub, cached between runs."""
    os.makedirs(FONT_DIR, exist_ok=True)
    for name, path in FONTS.items():
        dest = os.path.join(FONT_DIR, name)
        if not os.path.exists(dest):
            url = f"https://raw.githubusercontent.com/google/fonts/main/{path}"
            with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as fh:
                fh.write(resp.read())


def grain_uri(size=512, seed=3):
    """Subtle film grain tile, so flat colour doesn't look synthetic."""
    from PIL import Image
    rnd = random.Random(seed)
    img = Image.new("L", (size, size))
    img.putdata([int(max(0, min(255, rnd.gauss(128, 46)))) for _ in range(size * size)])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def split_name(name):
    """'Aventus Eau de Parfum 100ml' -> ('Aventus', 'Eau de Parfum · 100ml')."""
    size = re.search(r"\b(\d+(?:\.\d+)?\s?ml)\b", name, re.I)
    rest = name[:size.start()] + name[size.end():] if size else name
    conc = None
    low = rest.lower()
    for c in CONCENTRATIONS:
        i = low.find(c)
        if i > 0:
            conc = rest[i:i + len(c)]
            rest = rest[:i] + rest[i + len(c):]
            break
    title = re.sub(r"\s+", " ", rest).strip(" -·,") or name
    if conc and conc.lower() in ("edp", "edt"):
        conc = conc.upper()
    elif conc and conc.islower():
        conc = conc.capitalize()
    bits = [b for b in (conc,
                        size.group(1).replace(" ", "") if size else None) if b]
    return title, " · ".join(bits)


def _encode(page, out_path, frames, fps):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
           "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-maxrate", "12M", "-bufsize", "24M",
           "-profile:v", "high", "-tune", "animation",
           "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "128k",
           "-movflags", "+faststart", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(frames):
            page.evaluate(f"render({i / fps:.4f})")
            proc.stdin.write(page.screenshot(type="jpeg", quality=95))
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError("ffmpeg failed")


def build_reels(db, cfg, day, drops, social_dir, site_dir=None, publish=False):
    """Render one Reel per top drop. Returns manifest entries."""
    vcfg = cfg.get("video", {})
    count = vcfg.get("per_day", 3)
    if not drops or count <= 0:
        return []
    from playwright.sync_api import sync_playwright

    ensure_fonts()
    os.makedirs(social_dir, exist_ok=True)
    tpl = open(os.path.join(HERE, "engine", "reel.html"), encoding="utf-8").read()
    tpl = tpl.replace("__FONTS__", "file://" + FONT_DIR).replace("__GRAIN__", grain_uri())
    site = cfg["site"]
    host = site["base_url"].split("://")[-1].rstrip("/")
    entries = []
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        for i, d in enumerate(drops[:count], 1):
            pts = [p for _, p in history(db, d["id"], 30)] or [d["was"], d["price"]]
            title, detail = split_name(d["name"])
            data = {"sym": site["currency_symbol"], "pct": d["pct"], "brand": d["brand"], "title": title,
                    "detail": detail, "was": d["was"], "now": d["price"], "shop": d["merchant"],
                    "history": pts, "atl": bool(d.get("all_time_low")), "url": host, "dur": DURATION,
                    "image": d.get("image") or ""}
            html_path = os.path.join(tmp, f"reel_{i}.html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(tpl.replace("__DATA__", json.dumps(data)))
            page.goto("file://" + html_path)
            page.evaluate("() => document.fonts.ready.then(() => true)")
            out = os.path.join(social_dir, f"reel_{i}.mp4")
            _encode(page, out, int(DURATION * FPS), FPS)
            page.evaluate("render(5.0)")
            page.screenshot(path=os.path.join(social_dir, f"reel_{i}_cover.jpg"), type="jpeg", quality=92)
            entry = {"file": f"reel_{i}.mp4", "brand": d["brand"], "name": d["name"],
                     "caption": reel_caption(cfg, d), "thumb_offset_ms": 5000}
            if publish and site_dir:
                os.makedirs(os.path.join(site_dir, "reels"), exist_ok=True)
                shutil.copy(out, os.path.join(site_dir, "reels", f"{day}-{i}.mp4"))
                entry["url"] = f"{site['base_url'].rstrip('/')}/reels/{day}-{i}.mp4"
            entries.append(entry)
        browser.close()
    return entries


def reel_caption(cfg, d):
    sym = cfg["site"]["currency_symbol"]
    tag = re.sub(r"[^a-z0-9]", "", d["brand"].lower())
    low = "\nLowest price we've tracked." if d.get("all_time_low") else ""
    return (f"{d['brand']} {d['name']}: {sym}{d['price']:.2f} at {d['merchant']}, "
            f"down {d['pct']}% from its usual {sym}{d['was']:.2f}.{low}\n\n"
            f"Every drop we post is checked against 30 days of real prices. "
            f"Link in bio for today's full list.\n\n"
            f"#ad #theledgerdrops #fragrance #perfume #fragrancedeals #{tag} #ukdeals")
