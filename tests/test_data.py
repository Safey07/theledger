import pytest

from engine import data

FILTERS = {"merchants_allow": ["Good Shop"], "currency": "GBP", "min_price": 10,
           "include_keywords": ["eau de parfum", "fragrance", "gift set"],
           "exclude_keywords": ["car", "shower gel", "tester"]}


def product(**kw):
    base = {"name": "Good Girl Eau de Parfum 80ml", "category": "Women's Fragrance",
            "merchant": "Good Shop", "price": 80.0, "currency": "GBP"}
    return {**base, **kw}


@pytest.mark.parametrize("kw,ok", [
    ({}, True),
    ({"merchant": "good shop"}, True),                    # allowlist ignores case
    ({"merchant": "Other Shop"}, False),                  # not a retailer we've joined
    ({"currency": "EUR"}, False),                         # never show euros as pounds
    ({"currency": ""}, True),                             # feed didn't say: trust the feed's market
    ({"price": 9.99}, False),                             # under min_price
    ({"name": "Good Girl Shower Gel 200ml"}, False),      # junk word
    ({"name": "Good Girl Eau de Parfum 80ml Tester"}, False),
    ({"name": "Carolina Herrera Good Girl Eau de Parfum"}, True),   # whole words: 'car' != 'Carolina'
    ({"name": "Good Girl Lipstick", "category": "Make-up"}, False), # not a fragrance at all
])
def test_keep(kw, ok):
    assert data.keep(product(**kw), FILTERS) is ok


def test_empty_allowlist_allows_any_retailer():
    assert data.keep(product(merchant="Anyone"), {**FILTERS, "merchants_allow": []})


def _db_with(prices, merchant="Good Shop", pid="p1", in_stock=1):
    db = data.connect(":memory:")
    db.execute("INSERT INTO products (id,name,brand,merchant,slug) VALUES (?,?,?,?,?)",
               (pid, "Sauvage Eau de Parfum 100ml", "Dior", merchant, pid))
    for day, price in prices:
        db.execute("INSERT INTO prices VALUES (?,?,?,?,?)", (pid, day, price, None, in_stock))
    return db


RULES = {"min_drop_pct": 10, "min_drop_abs": 5, "history_days": 30}
HISTORY = [(f"2026-10-{d:02d}", 100.0) for d in range(1, 21)]


def test_detect_drops_flags_a_real_drop():
    db = _db_with(HISTORY + [("2026-10-21", 85.0)])
    (drop,) = data.detect_drops(db, "2026-10-21", RULES)
    assert drop["was"] == 100.0 and drop["saving"] == 15.0 and drop["pct"] == 15
    assert drop["all_time_low"] is True


@pytest.mark.parametrize("today", [95.0, 91.0])   # 5% off; 9% off (under 10%)
def test_detect_drops_ignores_small_moves(today):
    db = _db_with(HISTORY + [("2026-10-21", today)])
    assert data.detect_drops(db, "2026-10-21", RULES) == []


def test_detect_drops_needs_pounds_as_well_as_percent():
    db = _db_with([(d, 30.0) for d, _ in HISTORY] + [("2026-10-21", 26.0)])   # 13% but only £4
    assert data.detect_drops(db, "2026-10-21", RULES) == []


def test_detect_drops_needs_history_and_stock():
    assert data.detect_drops(_db_with([("2026-10-21", 50.0)]), "2026-10-21", RULES) == []
    assert data.detect_drops(_db_with(HISTORY + [("2026-10-21", 85.0)], in_stock=0), "2026-10-21", RULES) == []


def test_detect_drops_announces_a_price_once_a_month():
    db = _db_with(HISTORY + [("2026-10-21", 85.0), ("2026-10-22", 85.0), ("2026-10-23", 80.0)])
    data.mark_published(db, data.detect_drops(db, "2026-10-21", RULES), "2026-10-21")
    assert data.detect_drops(db, "2026-10-22", RULES) == []          # same price again: quiet
    assert len(data.detect_drops(db, "2026-10-23", RULES)) == 1      # it got cheaper: announce


def test_last_good_day_skips_retailers_we_no_longer_use():
    db = _db_with([("2026-10-10", 50.0)], merchant="Good Shop", pid="a")
    db.execute("INSERT INTO products (id,name,brand,merchant,slug) VALUES ('b','x','y','Old Network Shop','b')")
    db.execute("INSERT INTO prices VALUES ('b','2026-10-20',50.0,NULL,1)")
    assert data.last_good_day(db, "2026-10-22") == "2026-10-20"
    assert data.last_good_day(db, "2026-10-22", {"good shop"}) == "2026-10-10"
    assert data.last_good_day(db, "2026-10-22", {"nobody"}) is None


def test_allowed_merchants_includes_feed_lists_and_display_names():
    cfg = {"filters": {"merchants_allow": ["Space NK - UK"]},
           "feeds": [{"merchants_allow": ["The Fragrance Shop"]}, {"url": "x"}],
           "merchant_names": {"Space NK - UK": "Space NK"}}
    assert data.allowed_merchants(cfg) == {"space nk - uk", "space nk", "the fragrance shop"}
    cfg["feeds"].append({"merchants_allow": []})
    assert data.allowed_merchants(cfg) is None
