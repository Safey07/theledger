import os

import yaml

from engine import data
from engine.render import build_site

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build(tmp_path, demo=False, key="keep"):
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    if key != "keep":
        cfg["site"]["posthog_key"] = key
    db = data.connect(":memory:")
    out = tmp_path / "site"
    build_site(db, cfg, "2026-11-04", [], str(out), demo=demo)
    return out


def test_live_pages_load_cookieless_posthog(tmp_path):
    html = (_build(tmp_path) / "index.html").read_text()
    assert "posthog.init(" in html
    assert 'cookieless_mode: "always"' in html
    assert 'person_profiles: "never"' in html
    assert "https://eu.i.posthog.com" in html
    assert "affiliate_click" in html


def test_demo_build_has_no_analytics(tmp_path):
    html = (_build(tmp_path, demo=True) / "index.html").read_text()
    assert "posthog" not in html


def test_analytics_off_without_key(tmp_path):
    html = (_build(tmp_path, key="") / "index.html").read_text()
    assert "posthog" not in html


def test_privacy_page_discloses_analytics(tmp_path):
    out = _build(tmp_path)
    privacy = next(out.rglob("privacy.html")).read_text()
    assert "PostHog" in privacy
    assert "cookieless" in privacy


# ---- opt-out and ad labels -------------------------------------------------

import re


def test_analytics_checks_optout_before_init(tmp_path):
    html = (_build(tmp_path) / "index.html").read_text()
    flag = html.index('localStorage.getItem("ledger_analytics_optout")')
    assert flag < html.index("posthog.init(")
    assert "try {" in html[flag - 40:flag]
    assert "disable_session_recording: true" in html


def test_privacy_page_has_optout_control(tmp_path):
    privacy = next(_build(tmp_path).rglob("privacy.html")).read_text()
    assert "Turn off analytics on this browser" in privacy
    assert "Turn it back on" in privacy
    assert "Analytics is off on this browser" in privacy
    assert "ledger_analytics_optout" in privacy
    assert "Discard client IP data" in privacy  # reminder comment kept


def _sponsored_anchors(html):
    return re.findall(r'<a [^>]*rel="sponsored nofollow noopener"[^>]*>.*?</a>', html, re.S)


def _demo_site(tmp_path):
    """Real product pages from the bundled demo feeds (fictional retailers)."""
    import run
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    db = data.connect(":memory:")
    filters = {**cfg["filters"], "merchants_allow": []}
    feeds = run.build_demo(os.path.join(HERE, "sample_data"))
    for day, path in feeds[:-1]:
        data.ingest(db, [path], filters, day)
        data.mark_published(db, data.detect_drops(db, day, cfg["detection"]), day)
    day, last = feeds[-1]
    data.ingest(db, [last], filters, day)
    drops = data.detect_drops(db, day, cfg["detection"])
    out = tmp_path / "demosite"
    build_site(db, cfg, day, drops, str(out), demo=True)
    return out


def test_product_pages_label_every_affiliate_link(tmp_path):
    out = _demo_site(tmp_path)
    pages = list((out / "p").glob("*.html"))
    assert pages
    seen = 0
    for page in pages:
        html = page.read_text()
        for a in _sponsored_anchors(html):
            seen += 1
            assert '<span class="ad">(Ad)</span>' in a, a
        assert "Links marked (Ad) are affiliate links" in html
        assert "Links may earn us a commission" not in html
    assert seen >= len(pages)


def test_popular_page_labels_amazon_links(tmp_path):
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    cfg.setdefault("amazon", {})["tag"] = "t-21"
    cfg["amazon"]["picks"] = [{"g": "Men", "brand": "Dior", "name": "Sauvage"}]
    db = data.connect(":memory:")
    out = tmp_path / "site"
    build_site(db, cfg, "2026-11-04", [], str(out))
    html = (out / "popular.html").read_text()
    anchors = _sponsored_anchors(html)
    assert anchors
    assert all('<span class="ad">(Ad)</span>' in a for a in anchors)


def test_demo_product_pages_have_no_analytics(tmp_path):
    out = _demo_site(tmp_path)
    for page in (out / "p").glob("*.html"):
        assert "posthog" not in page.read_text()
