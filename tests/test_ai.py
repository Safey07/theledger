import copy
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import ai
from engine.video import reel_caption

CFG = {"site": {"currency_symbol": "£"}, "ai": {"enabled": True}}
DROP = {"brand": "Dior", "name": "Sauvage Eau de Parfum 100ml", "price": 79.0, "was": 99.0, "pct": 20,
        "merchant": "The Fragrance Shop", "all_time_low": False}
POSTS = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "content", "evergreen.yaml")))


def good_post():
    p = copy.deepcopy(next(p for p in POSTS if p["slug"] == "about"))
    p["slug"] = "storing-fragrance"
    return p


def test_no_key_means_no_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai.ask("hi", "claude-haiku-5-5") is None


def test_caption_falls_back_to_template_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cap = reel_caption(CFG, DROP)
    assert cap.startswith("Dior Sauvage") and "£79.00" in cap and "#ad" in cap


def test_good_hook_is_prepended_and_facts_stay(monkeypatch):
    monkeypatch.setattr(ai, "ask", lambda *a, **k: "Fresh, peppery and built for every day of the week.")
    cap = reel_caption(CFG, DROP)
    assert cap.startswith("Fresh, peppery")
    assert "£79.00 at The Fragrance Shop, down 20%" in cap and "#ad" in cap


def test_hooks_with_facts_are_rejected():
    for bad in ["Now only £79 at a top shop today", "Twenty percent off, 20% less than usual!",
                "Grab it now via https://x.co please", "A steal for anyone who loves this scent",
                "Short", "Fresh and spicy: a true icon"]:
        assert ai.clean_hook(bad) is None, bad


def test_clean_post_passes():
    assert ai.check_post(good_post(), {s["slug"] for s in POSTS}, ["Superdrug"]) == []


def test_invented_numbers_and_claims_are_rejected():
    p = good_post()
    p["slides"][1]["points"][0]["b"] = "A study found 73 percent of bottles fade in a year."
    issues = ai.check_post(p, set(), [])
    assert any("73" in i for i in issues) and any("study" in i for i in issues)


def test_retailer_names_and_reused_slugs_are_rejected():
    p = good_post()
    p["caption"] += "\nBuy it at Superdrug."
    p["slug"] = "about"
    issues = ai.check_post(p, {"about"}, ["Superdrug"])
    assert any("Superdrug" in i for i in issues) and any("already used" in i for i in issues)


def test_writer_keeps_only_checked_posts(monkeypatch):
    import json
    bad = good_post()
    bad["slug"] = "bad-one"
    bad["caption"] += "\nSave 47 pounds."
    monkeypatch.setattr(ai, "ask", lambda *a, **k: json.dumps([good_post(), bad]))
    good, rejected = ai.write_evergreen(CFG, POSTS, 2, [])
    assert [p["slug"] for p in good] == ["storing-fragrance"]
    assert len(rejected) == 1 and "47" in rejected[0]


def test_pasted_key_with_newline_is_cleaned(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return b'{"content":[{"type":"text","text":"ok"}]}'

    def fake_urlopen(req, timeout=0):
        seen["key"] = req.get_header("X-api-key")
        return Resp()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test\n\n")
    monkeypatch.setattr(ai.urllib.request, "urlopen", fake_urlopen)
    assert ai.ask("hi", "claude-haiku-5-5") == "ok"
    assert seen["key"] == "sk-test"
