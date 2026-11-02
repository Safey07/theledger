import os

import yaml

from engine import data
from engine.render import build_site

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _build(tmp_path, tag):
    cfg = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
    cfg.setdefault("amazon", {})["tag"] = tag
    db = data.connect(":memory:")
    out = tmp_path / "site"
    build_site(db, cfg, "2026-11-03", [], str(out))
    return out


def test_empty_pages_point_to_popular_when_amazon_tag_set(tmp_path):
    out = _build(tmp_path, "theledgeruk-21")
    shop = (out / "shop.html").read_text()
    assert 'href="popular.html"' in shop
    assert "See popular fragrances" in shop


def test_no_popular_link_without_amazon_tag(tmp_path):
    out = _build(tmp_path, "")
    shop = (out / "shop.html").read_text()
    assert "See popular fragrances" not in shop
    assert not (out / "popular.html").exists()
