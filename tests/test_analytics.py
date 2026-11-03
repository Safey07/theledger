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
