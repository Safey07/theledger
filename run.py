"""The Ledger: daily run.

    python run.py            live run: pull feeds, detect drops, build everything, send email
    python run.py --demo     rebuild from 31 days of invented sample data (no accounts needed)
"""
import argparse
import json
import os
import urllib.request
from datetime import date

import yaml

from engine import data, render, video
from engine.demo import build as build_demo

HERE = os.path.dirname(os.path.abspath(__file__))


def send_email(cfg, subject, html):
    provider = cfg["email"]["provider"]
    if provider == "none":
        print("email: provider is 'none', digest saved to file only")
        return
    key = os.environ.get(cfg["email"]["api_key_env"])
    if not key:
        print("email: no API key in environment, skipped")
        return
    if provider == "buttondown":
        req = urllib.request.Request(
            "https://api.buttondown.com/v1/emails",
            data=json.dumps({"subject": subject, "body": html, "status": "about_to_send"}).encode(),
            headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            print(f"email: sent via Buttondown ({resp.status})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--no-email", action="store_true")
    args = ap.parse_args()

    with open(os.path.join(HERE, "config.yaml")) as fh:
        cfg = yaml.safe_load(fh)
    cfg["signup_action"] = os.environ.get("SIGNUP_FORM_ACTION", "#")
    out = os.path.join(HERE, "output")

    if not args.demo and not any(data._expand_env(f["url"]) for f in cfg["feeds"]):
        print("No feed URL set yet, building the demo site instead.")
        args.demo = True

    if args.demo:
        db_path = os.path.join(HERE, "data", "demo.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        db = data.connect(db_path)
        feeds = build_demo(os.path.join(HERE, "sample_data"))
        demo_filters = {**cfg["filters"], "merchants_allow": []}   # demo retailers are fictional
        for day, path in feeds[:-1]:   # backfill history, publishing as we go
            data.ingest(db, [path], demo_filters, day)
            data.mark_published(db, data.detect_drops(db, day, cfg["detection"]), day)
        day, last = feeds[-1]
        count = data.ingest(db, [last], demo_filters, day)
    else:
        db = data.connect(os.path.join(HERE, "data", "prices.db"))
        day = date.today().isoformat()
        sources = [f["url"] for f in cfg["feeds"]]
        count = data.ingest(db, sources, cfg["filters"], day)

    drops = data.detect_drops(db, day, cfg["detection"])
    pages = render.build_site(db, cfg, day, drops, os.path.join(out, "site"), demo=args.demo)
    subject, html = render.build_digest(cfg, day, drops, os.path.join(out, "email", f"{day}.html"))
    social_dir = os.path.join(out, "social", day)
    cards = render.build_social(cfg, day, drops, social_dir)
    reels = []
    try:
        reels = video.build_reels(db, cfg, day, drops, social_dir, os.path.join(out, "site"),
                                  publish=not args.demo)
    except Exception as err:  # a video problem must never stop the site updating
        print(f"video: skipped ({err})")
    evergreen = []
    try:
        from engine import stills
        evergreen = stills.build_all(cfg, os.path.join(out, "site"))
    except Exception as err:  # never block the site on an image problem
        print(f"evergreen posts: skipped ({err})")
    with open(os.path.join(social_dir, "manifest.json"), "w") as fh:
        json.dump({"day": day, "demo": args.demo, "reels": reels, "evergreen": evergreen}, fh, indent=2)
    data.mark_published(db, drops, day)

    print(f"{day}: {count} prices stored, {len(drops)} drops, {pages} pages, {cards} social cards, {len(reels)} reels")
    print(f"email subject: {subject}")
    if drops and not args.demo and not args.no_email:
        send_email(cfg, subject, html)


if __name__ == "__main__":
    main()
