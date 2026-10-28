"""Amazon Associates links: only with a tag, always tagged, never with a price."""
from engine.content import amazon_link


def test_amazon_link_is_tagged_search():
    url = amazon_link("Dior", "Sauvage Eau de Toilette", "theledgeruk-21")
    assert url.startswith("https://www.amazon.co.uk/s?k=Dior+Sauvage+Eau+de+Toilette")
    assert url.endswith("&tag=theledgeruk-21")


def test_amazon_link_escapes_ampersand():
    url = amazon_link("Viktor&Rolf", "Flowerbomb", "x-21")
    assert "Viktor%26Rolf" in url and url.count("&") == 1
