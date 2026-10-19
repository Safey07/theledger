"""Post to the Facebook Page: today's top drop (video) or the next evergreen carousel.

Needs FB_PAGE_ID and FB_PAGE_TOKEN (a Page access token with pages_manage_posts).
Does nothing if they are missing. Never posts demo prices.
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
HOST = "https://graph.facebook.com"


def call(method, path, token, **params):
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = f"{HOST}{path}"
    req = (urllib.request.Request(f"{url}?{data.decode()}") if method == "GET"
           else urllib.request.Request(url, data=data, method="POST"))
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path.split('?')[0]} failed: {err.read().decode()[:400]}") from None


def main():
    page, token = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
    if not page or not token:
        print("Facebook not connected yet (FB_PAGE_ID / FB_PAGE_TOKEN missing). Skipping.")
        return
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    fcfg = cfg.get("facebook", {})
    if not fcfg.get("autopost", True):
        print("Facebook autopost is off in config.yaml. Skipping.")
        return
    v = fcfg.get("api_version", "v25.0")
    site = cfg["site"]["base_url"].replace("https://", "")
    path = os.path.join(HERE, "output", "social", date.today().isoformat(), "manifest.json")
    if not os.path.exists(path):
        print("No manifest for today. Skipping.")
        return
    manifest = json.load(open(path))
    if st.posted_today("facebook"):
        print("Already posted today. Skipping.")
        return

    me = call("GET", f"/{v}/{page}", token, fields="name")
    print(f"Facebook connected as page '{me.get('name')}'.")

    batch = int(os.environ.get("EVERGREEN_BATCH", "1") or 1) if manifest.get("demo") else 1
    todo = [i for i in st.todays_items(manifest) if not st.done("facebook", i["key"])][:batch]
    if not todo:
        print("Nothing new to post on Facebook today.")
        return
    for item in todo:
        text = st.web_caption(item["caption"], site)
        if item["kind"] == "video":
            res = call("POST", f"/{v}/{page}/videos", token, file_url=item["url"], description=text)
        else:
            ids = [call("POST", f"/{v}/{page}/photos", token, url=u, published="false")["id"]
                   for u in item["urls"]]
            media = {f"attached_media[{n}]": json.dumps({"media_fbid": i}) for n, i in enumerate(ids)}
            res = call("POST", f"/{v}/{page}/feed", token, message=text, **media)
        st.mark("facebook", item["key"])
        print(f"posted to Facebook: {item['key']} ({res.get('id') or res.get('post_id')})")
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        sys.exit(f"Facebook: {err}")
