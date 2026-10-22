"""Every supported feed format ingests the same way. Offline: fixtures only."""
import os

import pytest

from engine import data

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
FILTERS = {"currency": "GBP", "min_price": 10,
           "include_keywords": ["fragrance", "eau de parfum", "eau de toilette", "edp", "edt"],
           "exclude_keywords": ["shower gel", "deodorant", "hair mist", "bath"]}


def _db():
    return data.connect(":memory:")


def _rows(db):
    return {r["id"]: dict(r) for r in db.execute(
        "SELECT p.*, pr.price, pr.rrp, pr.in_stock FROM products p JOIN prices pr ON pr.product_id=p.id")}


def test_money_strings():
    assert data._money("12.99 GBP") == (12.99, "GBP")
    assert data._money("£1,049.00") == (1049.0, "GBP")
    assert data._money("GBP 30") == (30.0, "GBP")
    assert data._money("45.50") == (45.5, "")
    assert data._money("") == (None, "")


def test_awin():
    db = _db()
    feed = {"name": "awin", "url": os.path.join(FIX, "awin.csv"), "format": "awin"}
    assert data.ingest(db, [feed], FILTERS, "2026-10-01") == 2   # shower gel and EUR row dropped
    rows = _rows(db)
    assert rows["9001-101"]["brand"] == "Dior" and rows["9001-101"]["name"] == "Sauvage Eau de Parfum 100ml"
    assert rows["9001-101"]["price"] == 89.0 and rows["9001-101"]["rrp"] == 115.0
    assert rows["9001-102"]["in_stock"] == 0


def test_bare_path_is_read_as_awin():
    db = _db()
    assert data.ingest(db, [os.path.join(FIX, "awin.csv")], FILTERS, "2026-10-01") == 2


@pytest.mark.parametrize("name", ["rakuten.csv", "rakuten.xml"])
def test_rakuten(name):
    db = _db()
    feed = {"name": "tfs", "url": os.path.join(FIX, name), "format": "rakuten",
            "merchant": "The Fragrance Shop", "currency": "GBP"}
    assert data.ingest(db, [feed], FILTERS, "2026-10-01") == 2
    rows = _rows(db)
    first = rows["tfs-TFS1"]
    assert first["merchant"] == "The Fragrance Shop"
    assert first["price"] == 89.0 and first["rrp"] == 115.0     # sale price wins, regular kept as rrp
    assert first["url"] == "https://example.com/r1" and first["image"] == "https://example.com/r1.jpg"
    assert rows["tfs-TFS2"]["in_stock"] == 0 and rows["tfs-TFS2"]["rrp"] is None


def test_generic_csv_column_map():
    db = _db()
    feed = {"name": "shop", "url": os.path.join(FIX, "generic.csv"), "format": "generic_csv",
            "delimiter": ";", "merchant": "Generic Shop",
            "columns": {"id": "SKU", "name": "Product", "brand": "Maker", "price": "Cost",
                        "url": "Url", "image": "Picture", "in_stock": "Stock"}}
    assert data.ingest(db, [feed], FILTERS, "2026-10-01") == 1   # hair mist excluded
    row = _rows(db)["shop-G1"]
    assert row["merchant"] == "Generic Shop" and row["price"] == 104.0 and row["in_stock"] == 1


def test_per_feed_allowlist_overrides_global():
    db = _db()
    feed = {"name": "tfs", "url": os.path.join(FIX, "rakuten.csv"), "format": "rakuten",
            "merchant": "The Fragrance Shop", "merchants_allow": ["The Fragrance Shop"]}
    assert data.ingest(db, [feed], {**FILTERS, "merchants_allow": ["Someone Else"]}, "2026-10-01") == 2
    assert data.ingest(db, [{**feed, "merchants_allow": []}],
                       {**FILTERS, "merchants_allow": ["Someone Else"]}, "2026-10-02") == 2
    assert data.ingest(db, [{k: v for k, v in feed.items() if k != "merchants_allow"}],
                       {**FILTERS, "merchants_allow": ["Someone Else"]}, "2026-10-03") == 0


def test_display_names():
    db = _db()
    feed = {"name": "awin", "url": os.path.join(FIX, "awin.csv"), "format": "awin"}
    data.ingest(db, [feed], FILTERS, "2026-10-01", names={"Test Shop": "Test"})
    assert {r["merchant"] for r in _rows(db).values()} == {"Test"}


def test_dead_or_unset_feeds_store_nothing(monkeypatch, capsys):
    monkeypatch.delenv("NOPE_FEED_URL", raising=False)
    db = _db()
    feeds = [{"name": "unset", "url": "${NOPE_FEED_URL}", "format": "rakuten"},
             {"name": "dead", "url": os.path.join(FIX, "missing.csv"), "format": "rakuten"},
             {"name": "odd", "url": os.path.join(FIX, "awin.csv"), "format": "nope"}]
    assert data.ingest(db, feeds, FILTERS, "2026-10-01") == 0
    out = capsys.readouterr().out
    assert "::warning::Feed dead failed" in out and "unknown format" in out
    assert "missing.csv" not in out     # never print feed locations, real ones carry keys
