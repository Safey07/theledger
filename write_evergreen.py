"""Top up content/evergreen.yaml with new AI-written carousels.

    python write_evergreen.py            write ai.evergreen_per_run new posts if the queue is low
    python write_evergreen.py --force    write them even if the queue is full

Run weekly by .github/workflows/evergreen.yml, which opens a pull request so a person
approves every post before it can go live. Needs ANTHROPIC_API_KEY. Does nothing without it.
"""
import argparse
import json
import os
import sys

import yaml

from engine import ai

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "content", "evergreen.yaml")


def unposted(posts):
    """Evergreen posts no platform has published yet (Facebook and TikTok track them in social_state)."""
    try:
        state = json.load(open(os.path.join(HERE, "data", "social_state.json")))
    except (OSError, ValueError):
        state = {}
    done = set()
    for platform in ("facebook", "tiktok", "instagram"):
        done |= {k.split(":", 1)[1] for k in state.get(platform, []) if k.startswith("evergreen:")}
    return [p for p in posts if p["slug"] not in done]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    settings = ai.settings(cfg)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY. Skipping.")
        return
    posts = yaml.safe_load(open(PATH, encoding="utf-8")) or []
    queue = len(unposted(posts))
    want = int(settings.get("evergreen_per_run", 7))
    if queue >= int(settings.get("evergreen_min_queue", 7)) and not args.force:
        print(f"{queue} evergreen posts still waiting. Nothing to write.")
        return

    retailers = list(cfg["filters"].get("merchants_allow", [])) + list((cfg.get("merchant_names") or {}).values())
    retailers += [f.get("merchant", "") for f in cfg.get("feeds", [])] + ["Amazon"]
    good, bad = ai.write_evergreen(cfg, posts, want, retailers)
    for reason in bad:
        print(f"rejected: {reason}")
    if not good:
        print("::warning::No new evergreen posts passed the checks.")
        sys.exit(1 if bad else 0)

    with open(PATH, "a", encoding="utf-8") as fh:
        fh.write("\n# Written by Claude on " + __import__("datetime").date.today().isoformat()
                 + ". Approved by merging the pull request.\n")
        fh.write(yaml.safe_dump(good, allow_unicode=True, sort_keys=False, width=110))
    print(f"added {len(good)} posts: {', '.join(p['slug'] for p in good)}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(f"Added {len(good)} evergreen posts.\n\n")
            for p in good:
                fh.write(f"### {p['slug']}\n\n{p['caption']}\n\n")


if __name__ == "__main__":
    main()
