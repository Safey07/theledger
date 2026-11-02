"""Claude API helpers. Paid from the monthly API credits on the Max plan.

Every function here is optional: with no ANTHROPIC_API_KEY, or on any API error,
it returns None and the caller keeps its plain template. A failed AI call never
stops the site, the email or a post.

Hard rule: AI writes words, never facts. Prices, percentages, retailers and stats
always come from our own data. Every AI text is checked before it is used.
"""
import json
import os
import re
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

VOICE = ("You write for The Ledger, an independent UK fragrance price tracker. "
         "Voice: calm, sharp, premium, British English. Short sentences. No emojis. "
         "No hype words like 'insane', 'steal' or 'grab it now'. No colons or em dashes.")


def settings(cfg):
    ai = dict(cfg.get("ai") or {})
    ai.setdefault("enabled", True)
    ai.setdefault("caption_model", "claude-haiku-5-5")
    ai.setdefault("writer_model", "claude-opus-5-5")
    return ai


def ask(prompt, model, system=VOICE, max_tokens=600, key=None):
    """One Messages API call. Returns the text, or None if there is no key or anything fails."""
    key = key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": model, "max_tokens": max_tokens, "system": system,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        print(f"ai: API error {err.code}: {err.read().decode()[:200]}")
        return None
    except Exception as err:  # network, timeout, bad JSON
        print(f"ai: request failed ({err})")
        return None
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text").strip() or None


# ---------- Reel captions ----------

_BANNED = re.compile(r"[0-9£$€%#@]|https?://|www\.|\b(link in bio|steal|insane|hurry|last chance)\b", re.I)


def clean_hook(text):
    """A hook line is usable only if it carries no facts of its own: no numbers, prices, tags or links."""
    if not text:
        return None
    line = text.strip().strip('"').strip().splitlines()[0].strip()
    if not 15 <= len(line) <= 120 or _BANNED.search(line) or "—" in line or ":" in line:
        return None
    return line


def reel_hook(cfg, d):
    """A one-line opener for a price-drop Reel caption, or None. Facts stay in the template."""
    ai = settings(cfg)
    if not ai["enabled"]:
        return None
    prompt = (f"Write one opening line (max 15 words) for an Instagram caption about a price drop on "
              f"{d['brand']} {d['name']}.\n"
              f"{'It is the lowest price we have ever tracked for it.' if d.get('all_time_low') else ''}\n"
              "Say something true and evocative about the scent or the brand's style. "
              "Do not mention any price, number, percentage, retailer, hashtag or link. "
              "Reply with the line only.")
    return clean_hook(ask(prompt, ai["caption_model"], max_tokens=80))


# ---------- Evergreen carousel writer ----------

# Numbers we are allowed to say, because they are our own published rules.
_ALLOWED_NUMBERS = {"30", "10", "5"}
_CLAIMS = re.compile(r"\b(study|studies|survey|research shows|according to|percent of|statistic|scientists)\b", re.I)


def check_post(post, existing_slugs, retailers):
    """Return a list of problems with an AI-written evergreen post. Empty list = safe to queue."""
    problems = []
    if not isinstance(post, dict):
        return ["not an object"]
    slug = str(post.get("slug", ""))
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or len(slug) > 40:
        problems.append(f"bad slug {slug!r}")
    if slug in existing_slugs:
        problems.append(f"slug {slug!r} already used")
    slides = post.get("slides")
    if not isinstance(slides, list) or not 2 <= len(slides) <= 3:
        return problems + ["needs 2 or 3 slides"]
    hook = slides[0]
    if not all(isinstance(hook.get(k), str) and hook.get(k) for k in ("kicker", "title", "italic", "sub")):
        problems.append("hook slide needs kicker, title, italic and sub")
    for s in slides[1:]:
        pts = s.get("points")
        if not isinstance(s.get("title"), str) or not isinstance(pts, list) or not 2 <= len(pts) <= 3:
            problems.append("point slides need a title and 2-3 points")
            continue
        for p in pts:
            if not (isinstance(p, dict) and isinstance(p.get("h"), str) and isinstance(p.get("b"), str)):
                problems.append("each point needs h and b")
            elif len(p["h"]) > 45 or len(p["b"]) > 130:
                problems.append("a point is too long for the slide")
    if not isinstance(post.get("caption"), str) or len(post["caption"]) < 80:
        problems.append("caption missing or too short")

    text = json.dumps(post, ensure_ascii=False)
    for n in re.findall(r"\d+", text):
        if n not in _ALLOWED_NUMBERS:
            problems.append(f"contains the number {n} (no invented figures)")
    if re.search(r"[$€]", text):
        problems.append("contains a currency sign")
    if _CLAIMS.search(text):
        problems.append("cites a study or statistic")
    if "#" in text or "http" in text:
        problems.append("hashtags or links belong to the template, not the post")
    for r in retailers:
        if r and re.search(rf"\b{re.escape(r)}\b", text, re.I):
            problems.append(f"names retailer {r}")
    if "—" in text:
        problems.append("contains an em dash")
    return problems


def write_evergreen(cfg, existing, count, retailers):
    """Ask Claude for `count` new evergreen carousels. Returns (good_posts, rejected_reasons)."""
    ai = settings(cfg)
    slugs = {p["slug"] for p in existing}
    clean = [p for p in existing if not check_post(p, set(), retailers)]
    example = {k: clean[0][k] for k in ("slug", "caption", "slides")} if clean else {}
    covered = "\n".join(f"- {p['slug']}: {p['caption'].strip().splitlines()[0]}" for p in existing)
    prompt = f"""Write {count} new Instagram carousel posts for The Ledger, a UK fragrance price tracker.
They post on days with no price data, so they teach UK buyers how to buy fragrance well.

Topics already covered (do not repeat them):
{covered}

Good new angles: reading a bottle box, storing fragrance so it lasts, blind buying safely,
spotting a fake listing, seasonal scents, layering, gifting without overspending, what
"flanker" means, how to test a scent in store, niche versus designer value.

Strict rules, a checker rejects any post that breaks them:
- No numbers at all, except our own rules: 30-day price history, at least 10% and £5 below it.
- No invented facts, studies, surveys, statistics or quotes. Only general buying advice.
- No retailer names, no prices, no hashtags, no links, no emojis, no em dashes.
- British English. Calm, premium, useful.
- slug: lowercase-with-hyphens, max 40 chars.
- caption: 3 short paragraphs, first line is the hook, end with the line "theledgeruk.co.uk (link in bio)".
- slides: exactly 2 or 3. Slide 1 has kicker, title, italic, sub. The others have title and 2 or 3 points,
  each point has h (max 45 chars) and b (max 130 chars).

Here is an existing post as the exact shape to follow:
{json.dumps(example, ensure_ascii=False, indent=1)}

Reply with a JSON array of {count} posts and nothing else."""
    text = ask(prompt, ai["writer_model"], max_tokens=6000)
    if not text:
        return [], ["no reply from the API"]
    m = re.search(r"\[.*\]", text, re.S)
    try:
        posts = json.loads(m.group(0)) if m else []
    except ValueError:
        return [], ["reply was not valid JSON"]
    good, bad = [], []
    for post in posts:
        issues = check_post(post, slugs, retailers)
        if issues:
            bad.append(f"{post.get('slug', '?') if isinstance(post, dict) else '?'}: {'; '.join(issues)}")
        else:
            slugs.add(post["slug"])
            good.append({"slug": post["slug"], "caption": post["caption"].strip() + "\n",
                         "slides": post["slides"]})
    return good, bad
