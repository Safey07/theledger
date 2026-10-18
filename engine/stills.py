"""Render evergreen Instagram carousels (1080x1350) from content/evergreen.yaml.

Used on days with no real price data, so the account keeps posting.
Same dark-and-gold look as the Reels. Text only, drawn with Pillow.
"""
import os

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .video import FONT_DIR, ensure_fonts

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1350
BG, CREAM, GOLD, MUTED = "#12100e", "#f3ece1", "#c2a266", "#8d8173"


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    return lines + [cur] if cur else lines


def _canvas():
    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.15, -H * 0.2, W * 0.85, H * 0.55], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.composite(Image.new("RGB", (W, H), "#2b2219"), img, glow)
    noise = Image.effect_noise((W, H), 6).convert("RGB")
    img = Image.blend(img, noise, 0.03)
    return img


def _footer(draw, index, total, handle):
    draw.text((80, H - 92), "THE LEDGER", font=_font("Inter.ttf", 22), fill=GOLD)
    draw.text((W - 80, H - 92), f"{index}/{total}", font=_font("Inter.ttf", 22), fill=MUTED, anchor="ra")
    draw.line([(80, H - 120), (W - 80, H - 120)], fill="#2e2822", width=1)


def _hook(slide, index, total, handle):
    img = _canvas()
    d = ImageDraw.Draw(img)
    y = 300
    if slide.get("kicker"):
        d.text((80, y), slide["kicker"].upper(), font=_font("Inter.ttf", 26), fill=GOLD)
        d.line([(80, y + 52), (160, y + 52)], fill=GOLD, width=2)
        y += 120
    f = _font("Cormorant.ttf", 104)
    for line in _wrap(d, slide["title"], f, W - 160):
        d.text((80, y), line, font=f, fill=CREAM)
        y += 112
    if slide.get("italic"):
        fi = _font("CormorantItalic.ttf", 104)
        for line in _wrap(d, slide["italic"], fi, W - 160):
            d.text((80, y), line, font=fi, fill=GOLD)
            y += 112
    d.text((80, H - 200), "Swipe  →", font=_font("Inter.ttf", 26), fill=MUTED)
    _footer(d, index, total, handle)
    return img


def _point(slide, index, total, handle):
    img = _canvas()
    d = ImageDraw.Draw(img)
    d.text((80, 280), f"{index - 1:02d}", font=_font("Cormorant.ttf", 72), fill=GOLD)
    y = 380
    f = _font("Cormorant.ttf", 84)
    for line in _wrap(d, slide["title"], f, W - 160):
        d.text((80, y), line, font=f, fill=CREAM)
        y += 92
    y += 30
    fb = _font("Inter.ttf", 36)
    for line in _wrap(d, slide["body"], fb, W - 180):
        d.text((80, y), line, font=fb, fill="#d9d0c3")
        y += 54
    _footer(d, index, total, handle)
    return img


def _cta(index, total, handle, site_name, base_url):
    img = _canvas()
    d = ImageDraw.Draw(img)
    d.text((W // 2, 460), "Every morning.", font=_font("Cormorant.ttf", 96), fill=CREAM, anchor="mm")
    d.text((W // 2, 560), "Only the real drops.", font=_font("CormorantItalic.ttf", 96), fill=GOLD, anchor="mm")
    d.text((W // 2, 720), f"Follow @{handle}", font=_font("Inter.ttf", 36), fill=CREAM, anchor="mm")
    d.text((W // 2, 780), base_url.replace("https://", ""), font=_font("Inter.ttf", 30), fill=MUTED, anchor="mm")
    _footer(d, index, total, handle)
    return img


def build_all(cfg, site_dir):
    """Render every evergreen post into site_dir/posts/<slug>/N.jpg. Returns post list with public URLs."""
    ensure_fonts()
    path = os.path.join(HERE, "content", "evergreen.yaml")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        posts = yaml.safe_load(fh) or []
    base = cfg["site"]["base_url"].rstrip("/")
    handle = cfg["site"].get("instagram", "")
    out = []
    for post in posts:
        slides = post["slides"]
        total = len(slides) + 1
        folder = os.path.join(site_dir, "posts", post["slug"])
        os.makedirs(folder, exist_ok=True)
        urls = []
        for i, slide in enumerate(slides, 1):
            img = _hook(slide, i, total, handle) if i == 1 else _point(slide, i, total, handle)
            p = os.path.join(folder, f"{i}.jpg")
            img.save(p, quality=92)
            urls.append(f"{base}/posts/{post['slug']}/{i}.jpg")
        _cta(total, total, handle, cfg["site"]["name"], base).save(os.path.join(folder, f"{total}.jpg"), quality=92)
        urls.append(f"{base}/posts/{post['slug']}/{total}.jpg")
        caption = post["caption"].strip() + "\n\n#fragrance #perfume #fragrancetips #ukdeals #perfumetok #fragrancecommunity #theledgernotes"
        out.append({"slug": post["slug"], "caption": caption, "urls": urls})
    return out
