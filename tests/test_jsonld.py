import json

from engine.render import _product_jsonld, _site_jsonld


def listing(merchant, price, image=""):
    return {"brand": "Dior", "name": "Sauvage Eau de Parfum 100ml", "merchant": merchant,
            "price": price, "image": image, "slug": f"dior-sauvage-{merchant.lower()}"}


def nulls(obj):
    if isinstance(obj, dict):
        return any(v is None or nulls(v) for v in obj.values())
    if isinstance(obj, list):
        return any(nulls(v) for v in obj)
    return False


def test_product_jsonld_is_an_aggregate_offer_without_nulls():
    compare = [listing("A", 79.0), listing("B", 85.5, "https://example.com/b.jpg")]
    data = json.loads(_product_jsonld(compare[0], compare, base_url="https://example.co.uk/"))
    assert data["@type"] == "Product" and data["name"] == "Dior Sauvage Eau de Parfum 100ml"
    assert data["brand"] == {"@type": "Brand", "name": "Dior"}
    assert data["offers"] == {"@type": "AggregateOffer", "priceCurrency": "GBP",
                              "lowPrice": "79.00", "highPrice": "85.50", "offerCount": 2}
    assert data["image"] == "https://example.com/b.jpg"       # borrowed from another listing
    assert data["url"] == "https://example.co.uk/p/dior-sauvage-a.html"
    assert not nulls(data)
    assert "aggregateRating" not in data and "review" not in data   # we have none, never invent them


def test_product_jsonld_leaves_out_missing_fields():
    p = {**listing("A", 79.0), "brand": ""}
    data = json.loads(_product_jsonld(p, [p]))
    assert "image" not in data and "brand" not in data
    assert "across" not in data["description"]
    assert not nulls(data)


def test_product_jsonld_dates_stale_prices():
    p = listing("A", 79.0)
    assert "Lowest on 20 October 2026" in json.loads(_product_jsonld(p, [p], "20 October 2026"))["description"]


def test_jsonld_cannot_close_its_script_tag():
    p = {**listing("A", 79.0), "name": "</script><script>alert(1)"}
    assert "</script" not in _product_jsonld(p, [p])


def test_site_jsonld_has_search_action():
    data = json.loads(_site_jsonld({"name": "The Ledger", "base_url": "https://example.co.uk",
                                    "tagline": "t", "instagram": "x", "contact_email": ""}))
    org, web = data["@graph"]
    assert org["sameAs"] == ["https://www.instagram.com/x/"] and "email" not in org
    action = web["potentialAction"]
    assert action["target"]["urlTemplate"] == "https://example.co.uk/shop.html?q={search_term_string}"
    assert action["query-input"] == "required name=search_term_string"
    assert not nulls(data)
