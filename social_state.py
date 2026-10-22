"""Remembers what has already been posted on each platform (data/social_state.json).

Committed back to the repo after each run, so a post never goes out twice.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "social_state.json")


def load():
    try:
        with open(PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def done(platform, key):
    return key in load().get(platform, [])


def posted_today(platform):
    """True if this platform already got its post today. Scheduled retries then skip it;
    a hand-started run (Run workflow) can still post more."""
    from datetime import date
    if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return False
    return load().get("last", {}).get(platform) == date.today().isoformat()


def mark(platform, key):
    from datetime import date
    state = load()
    state.setdefault(platform, [])
    if key not in state[platform]:
        state[platform].append(key)
    state.setdefault("last", {})[platform] = date.today().isoformat()
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)


def save_secret(name, value):
    """Store a rotated token as a repo secret. Needs GH_SECRETS_TOKEN. Never prints the value."""
    pat = os.environ.get("GH_SECRETS_TOKEN")
    if not pat:
        print(f"WARNING: GH_SECRETS_TOKEN is not set, so the new {name} could not be saved")
        return False
    res = subprocess.run(["gh", "secret", "set", name, "--body", value,
                          "--repo", os.environ.get("GITHUB_REPOSITORY", "")],
                         env={**os.environ, "GH_TOKEN": pat}, capture_output=True)
    print(f"saved {name} to repo secrets" if res.returncode == 0 else f"could not save {name}")
    return res.returncode == 0


def todays_items(manifest, limit_reels=1):
    """What to post today: real drops as videos, or the next evergreen carousel when there are none."""
    if manifest.get("no_drops", manifest.get("demo")):
        return [{"kind": "carousel", "key": f"evergreen:{p['slug']}", "caption": p["caption"],
                 "urls": p["urls"]} for p in manifest.get("evergreen", [])]
    return [{"kind": "video", "key": f"reel:{manifest['day']}:{r['file']}", "caption": r["caption"],
             "url": r["url"]} for r in manifest.get("reels", []) if r.get("url")][:limit_reels]


def web_caption(caption, site):
    """Instagram says 'link in bio'. Facebook and TikTok get the real address."""
    return caption.replace(" (link in bio)", "").replace("Link in bio for", f"See {site} for")
