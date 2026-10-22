from engine.classify import clean_brand, clean_name, match_key


def test_clean_brand_merges_spellings():
    assert clean_brand("CHANEL") == "Chanel"
    assert clean_brand("christian dior") == "Dior"
    assert clean_brand("YSL") == "Yves Saint Laurent"
    assert clean_brand("  Tom   Ford ") == "Tom Ford"


def test_clean_name_drops_brand_and_expands_concentration():
    assert clean_name("Dior", "Dior Sauvage EDT 100ml") == "Sauvage Eau de Toilette 100ml"
    assert clean_name("Yves Saint Laurent", "YSL Libre Eau de Parfum 90ml Spray") == "Libre Eau de Parfum 90ml"
    assert clean_name("Chanel", "Bleu de Chanel EDP Natural Spray 100ml") == "Bleu de Chanel Eau de Parfum 100ml"


def test_clean_name_never_returns_blank():
    assert clean_name("Dior", "Dior") == "Dior"


def test_same_bottle_at_two_shops_matches():
    a = clean_name("Dior", "Dior Sauvage EDP 100ml")
    b = clean_name("Dior", "Sauvage Eau de Parfum 100ml Spray")
    assert match_key("Dior", a) == match_key("Dior", b) == "dior|sauvage|Eau de Parfum|100"


def test_size_and_concentration_keep_bottles_apart():
    edp100 = match_key("Dior", "Sauvage Eau de Parfum 100ml")
    assert edp100 != match_key("Dior", "Sauvage Eau de Parfum 60ml")
    assert edp100 != match_key("Dior", "Sauvage Eau de Toilette 100ml")
    assert edp100 != match_key("Chanel", "Sauvage Eau de Parfum 100ml")
