"""Post to TikTok via the Content Posting API: today's top drop (video) or the next evergreen photo post.

Needs TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN, plus GH_SECRETS_TOKEN
so the rotating refresh token can be saved. Does nothing if they are missing.

Until TikTok audits the app, it only allows private ("Only me") posts. The script asks TikTok
which privacy levels are allowed and uses PUBLIC_TO_EVERYONE as soon as it is offered.

One-off setup:  python post_tiktok.py --exchange CODE
turns the code shown on theledgeruk.co.uk/tiktok-callback.html into a saved refresh token.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

import yaml

import social_state as st

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://open.tiktokapis.com"
REDIRECT = "https://theledgeruk.co.uk/tiktok-callback.html"


def _post(path, body, token=None, form=False):
    if form:
        data, ctype = urllib.parse.urlencode(body).encode(), "application/x-www-form-urlencoded"
    else:
        data, ctype = json.dumps(body).encode(), "application/json; charset=UTF-8"
    req = urllib.request.Request(f"{API}{path}", data=data, method="POST", headers={"Content-Type": ctype})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"POST {path} failed: {err.read().decode()[:300]}") from None
    errinfo = out.get("error") or {}
    if isinstance(errinfo, dict) and errinfo.get("code") not in (None, "", "ok"):
        raise RuntimeError(f"POST {path}: {errinfo.get('code')} {errinfo.get('message', '')[:200]}")
    if "error_description" in out:
        raise RuntimeError(f"POST {path}: {out.get('error')} {out.get('error_description')[:200]}")
    return out


def _keys():
    return os.environ.get("TIKTOK_CLIENT_KEY"), os.environ.get("TIKTOK_CLIENT_SECRET")


def exchange(code):
    key, secret = _keys()
    if not key or not secret:
        sys.exit("Add TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET secrets first.")
    res = _post("/v2/oauth/token/", {"client_key": key, "client_secret": secret, "code": code.strip(),
                                     "grant_type": "authorization_code", "redirect_uri": REDIRECT}, form=True)
    if not st.save_secret("TIKTOK_REFRESH_TOKEN", res["refresh_token"]):
        sys.exit("Could not save the TikTok token. Add GH_SECRETS_TOKEN and try again with a new code.")
    print(f"TikTok connected. Scopes: {res.get('scope')}")


def access_token():
    key, secret = _keys()
    refresh = os.environ.get("TIKTOK_REFRESH_TOKEN")
    res = _post("/v2/oauth/token/", {"client_key": key, "client_secret": secret,
                                     "grant_type": "refresh_token", "refresh_token": refresh}, form=True)
    if res.get("refresh_token") and res["refresh_token"] != refresh:
        st.save_secret("TIKTOK_REFRESH_TOKEN", res["refresh_token"])
    return res["access_token"]


def _wait(token, publish_id):
    for _ in range(20):
        time.sleep(15)
        s = _post("/v2/post/publish/status/fetch/", {"publish_id": publish_id}, token).get("data", {})
        status = s.get("status")
        if status == "PUBLISH_COMPLETE" or status == "SEND_TO_USER_INBOX":
            return status
        if status == "FAILED":
            raise RuntimeError(f"TikTok rejected the post: {s.get('fail_reason')}")
    raise RuntimeError("TikTok took too long to process the post.")


def main():
    key, secret = _keys()
    if not key or not secret or not os.environ.get("TIKTOK_REFRESH_TOKEN"):
        print("TikTok not connected yet (TIKTOK_* secrets missing). Skipping.")
        return
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    tcfg = cfg.get("tiktok", {})
    if not tcfg.get("autopost", True):
        print("TikTok autopost is off in config.yaml. Skipping.")
        return
    site = cfg["site"]["base_url"].replace("https://", "")
    path = os.path.join(HERE, "output", "social", date.today().isoformat(), "manifest.json")
    if not os.path.exists(path):
        print("No manifest for today. Skipping.")
        return
    manifest = json.load(open(path))
    if st.posted_today("tiktok"):
        print("Already posted today. Skipping.")
        return

    token = access_token()
    info = _post("/v2/post/publish/creator_info/query/", {}, token).get("data", {})
    options = info.get("privacy_level_options", [])
    privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in options else "SELF_ONLY"
    print(f"TikTok connected as @{info.get('creator_username')}. Posting as {privacy}"
          + ("" if privacy.startswith("PUBLIC") else " (app not audited yet, so posts stay private)."))

    batch = int(os.environ.get("EVERGREEN_BATCH", "1") or 1) if manifest.get("no_drops", manifest.get("demo")) else 1
    todo = [i for i in st.todays_items(manifest) if not st.done("tiktok", i["key"])][:batch]
    if not todo:
        print("Nothing new to post on TikTok today.")
        return
    for item in todo:
        text = st.web_caption(item["caption"], site)
        title = text.splitlines()[0][:90]
        if item["kind"] == "video":
            res = _post("/v2/post/publish/video/init/", {
                "post_info": {"title": text[:2200], "privacy_level": privacy, "disable_comment": False},
                "source_info": {"source": "PULL_FROM_URL", "video_url": item["url"]}}, token)
        else:
            res = _post("/v2/post/publish/content/init/", {
                "post_info": {"title": title, "description": text[:4000], "privacy_level": privacy,
                              "disable_comment": False, "auto_add_music": True},
                "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0,
                                "photo_images": item["urls"]},
                "post_mode": "DIRECT_POST", "media_type": "PHOTO"}, token)
        status = _wait(token, res["data"]["publish_id"])
        st.mark("tiktok", item["key"])
        print(f"posted to TikTok: {item['key']} ({status}, {privacy})")


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--exchange":
            exchange(sys.argv[2])
        else:
            main()
    except RuntimeError as err:
        sys.exit(f"TikTok: {err}")
