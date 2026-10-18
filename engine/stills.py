"""Render evergreen Instagram carousels (1080x1350) from content/evergreen.yaml.

Used on days with no real price data, so the account keeps posting.
Same dark-and-gold look as the Reels. Dense, 2-3 slides per post.
"""
import os

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .video import FONT_DIR, ensure_fonts

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1080, 1350
M = 84  # side margin
BG, CREAM, GOLD, MUTED, BODY = "#12100e", "#f3ece1", "#c2a266", "#8d8173", "#d9d0c3"


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
    ImageDraw.Draw(glow).ellipse([W * 0.1, -H * 0.15, W * 0.9, H * 0.6], fill=95)
    glow = glow.filter(ImageFilter.GaussianBlur(220))
    img = Image.composite(Image.new("RGB", (W, H), "#2b2219"), img, glow)
    noise = Image.effect_noise((W, H), 6).convert("RGB")
    img = Image.blend(img, noise, 0.03)
    return img


def _frame(draw, index, total, handle, site):
    """Header wordmark and footer on every slide, so nothing feels bare."""
    draw.text((M, 72), "THE LEDGER", font=_font("Inter.ttf", 24), fill=GOLD)
    draw.text((W - M, 72), f"{index} / {total}", font=_font("Inter.ttf", 24), fill=MUTED, anchor="ra")
    draw.line([(M, 118), (W - M, 118)], fill="#2e2822", width=1)
    draw.line([(M, H - 128), (W - M, H - 128)], fill="#2e2822", width=1)
    draw.text((M, H - 96), site, font=_font("Inter.ttf", 24), fill=CREAM)
    draw.text((W - M, H - 96), f"@{handle}", font=_font("Inter.ttf", 24), fill=MUTED, anchor="ra")


def _hook(slide, index, total, handle, site):
    img = _canvas()
    d = ImageDraw.Draw(img)
    f_title = _font("Cormorant.ttf", 112)
    f_ital = _font("CormorantItalic.ttf", 112)
    f_sub = _font("Inter.ttf", 32)
    t_lines = _wrap(d, slide["title"], f_title, W - 2 * M)
    i_lines = _wrap(d, slide.get("italic", ""), f_ital, W - 2 * M) if slide.get("italic") else []
    s_lines = _wrap(d, slide.get("sub", ""), f_sub, W - 2 * M) if slide.get("sub") else []
    block = 90 + len(t_lines) * 120 + len(i_lines) * 120 + (40 + len(s_lines) * 46 if s_lines else 0)
    y = (H - block) // 2 - 20
    if slide.get("kicker"):
        d.text((M, y), slide["kicker"].upper(), font=_font("Inter.ttf", 28), fill=GOLD)
        d.line([(M, y + 56), (M + 72, y + 56)], fill=GOLD, width=2)
    y += 90
    for line in t_lines:
        d.text((M, y), line, font=f_title, fill=CREAM)
        y += 120
    for line in i_lines:
        d.text((M, y), line, font=f_ital, fill=GOLD)
        y += 120
    if s_lines:
        y += 40
        for line in s_lines:
            d.text((M, y), line, font=f_sub, fill=BODY)
            y += 46
    d.text((W - M, H - 190), "swipe →", font=_font("Inter.ttf", 26), fill=MUTED, anchor="ra")
    _frame(d, index, total, handle, site)
    return img


def _points(slide, index, total, handle, site):
    img = _canvas()
    d = ImageDraw.Draw(img)
    f_t, f_h, f_b, f_n = _font("Cormorant.ttf", 88), _font("Cormorant.ttf", 66), _font("Inter.ttf", 36), _font("Cormorant.ttf", 58)
    x = M + 100
    pts = slide.get("points", [])[:3]
    gap = 36

    def layout(draw_it, y):
        if draw_it:
            d.text((M, y), slide["title"], font=f_t, fill=CREAM)
        y += 140
        for i, p in enumerate(pts, 1):
            if draw_it:
                d.text((M, y + 4), f"{i:02d}", font=f_n, fill=GOLD)
            for line in _wrap(d, p["h"], f_h, W - x - M):
                if draw_it:
                    d.text((x, y), line, font=f_h, fill=CREAM)
                y += 72
            y += 8
            for line in _wrap(d, p["b"], f_b, W - x - M):
                if draw_it:
                    d.text((x, y), line, font=f_b, fill=BODY)
                y += 52
            if i < len(pts):
                y += gap
                if draw_it:
                    d.line([(x, y), (W - M, y)], fill="#3a322a", width=1)
                y += gap + 4
        return y

    height = layout(False, 0)
    top = 118 + ((H - 128 - 118) - height) // 2
    layout(True, top)
    _frame(d, index, total, handle, site)
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
    site = base.replace("https://", "")
    handle = cfg["site"].get("instagram", "")
    out = []
    for post in posts:
        slides = post["slides"]
        total = len(slides)
        folder = os.path.join(site_dir, "posts", post["slug"])
        os.makedirs(folder, exist_ok=True)
        urls = []
        for i, slide in enumerate(slides, 1):
            img = _hook(slide, i, total, handle, site) if i == 1 else _points(slide, i, total, handle, site)
            img.save(os.path.join(folder, f"{i}.jpg"), quality=92)
            urls.append(f"{base}/posts/{post['slug']}/{i}.jpg")
        caption = post["caption"].strip() + "\n\n#fragrance #perfume #fragrancetips #ukdeals #perfumetok #fragrancecommunity #theledgernotes"
        out.append({"slug": post["slug"], "caption": caption, "urls": urls})
    return out
