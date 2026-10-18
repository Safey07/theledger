"""Publish today's top Reel to Instagram (Instagram API with Instagram Login).

Does nothing unless IG_USER_ID and IG_ACCESS_TOKEN are set, and never posts
demo prices. Runs after the site deploys, because Instagram fetches the video
from its public URL on theledgeruk.co.uk.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = "https://graph.instagram.com"


def call(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{HOST}{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path} failed: {err.read().decode()[:400]}") from None


def refresh_token(token):
    """Long-lived tokens last 60 days. Refresh on every run so it never lapses."""
    try:
        res = call("GET", "/refresh_access_token", token, grant_type="ig_refresh_token")
    except RuntimeError as err:
        print(f"token refresh skipped: {err}")
        return token
    new = res.get("access_token", token)
    days = int(res.get("expires_in", 0)) // 86400
    print(f"token refreshed, valid for {days} more days")
    pat = os.environ.get("GH_SECRETS_TOKEN")
    if new != token and pat:
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--body", new,
                        "--repo", os.environ.get("GITHUB_REPOSITORY", "")],
                       env={**os.environ, "GH_TOKEN": pat}, check=False)
        print("saved refreshed token to repo secrets")
    elif new != token:
        print("WARNING: token changed but GH_SECRETS_TOKEN is not set, so it was not saved")
    return new


def wait_for_url(url, tries=20):
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(15)
    return False


def main():
    ig_id, token = os.environ.get("IG_USER_ID"), os.environ.get("IG_ACCESS_TOKEN")
    if not ig_id or not token:
        print("Instagram not connected yet (IG_USER_ID / IG_ACCESS_TOKEN missing). Skipping.")
        return
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    icfg = cfg.get("instagram", {})
    if not icfg.get("autopost", True):
        print("autopost is off in config.yaml. Skipping.")
        return
    version = icfg.get("api_version", "v25.0")
    day = date.today().isoformat()
    manifest_path = os.path.join(HERE, "output", "social", day, "manifest.json")
    if not os.path.exists(manifest_path):
        print("No manifest for today. Skipping.")
        return
    manifest = json.load(open(manifest_path))
    if manifest.get("demo"):
        print("Demo data. Never posting invented prices. Skipping.")
        return
    reels = [r for r in manifest.get("reels", []) if r.get("url")][: icfg.get("posts_per_day", 1)]
    if not reels:
        print("No drops worth posting today.")
        return

    token = refresh_token(token)
    base = f"/{version}/{ig_id}"

    recent = call("GET", f"{base}/media", token, fields="caption,timestamp", limit=10).get("data", [])
    today_utc = datetime.now(timezone.utc).date().isoformat()
    if any(m.get("timestamp", "").startswith(today_utc) and "#theledgerdrops" in (m.get("caption") or "")
           for m in recent):
        print("Already posted today. Skipping.")
        return

    for reel in reels:
        if not wait_for_url(reel["url"]):
            raise SystemExit(f"Video not reachable yet: {reel['url']}")
        box = call("POST", f"{base}/media", token, media_type="REELS", video_url=reel["url"],
                   caption=reel["caption"], share_to_feed="true",
                   thumb_offset=str(reel.get("thumb_offset_ms", 5000)))
        cid = box["id"]
        print(f"container {cid} created, processing")
        for _ in range(12):
            time.sleep(30)
            status = call("GET", f"/{version}/{cid}", token, fields="status_code").get("status_code")
            print(f"  status {status}")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise SystemExit(f"Instagram could not process the video: {status}")
        else:
            raise SystemExit("Instagram took too long to process the video.")
        pub = call("POST", f"{base}/media_publish", token, creation_id=cid)
        print(f"published Reel {pub.get('id')}: {reel['brand']} {reel['name']}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        sys.exit(str(err))
