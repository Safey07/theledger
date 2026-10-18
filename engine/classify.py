"""Work out who a fragrance is for, whether it's niche, and its size, from feed text."""
import re

WOMEN = ["women", "woman", "for her", "pour femme", "femme", "ladies", "her ", "miss dior", "mademoiselle",
         "la vie est belle", "good girl", "black opium", "libre", "j'adore", "flowerbomb", "bloom", "idole",
         "my way", "alien", "daisy", "chance", "n°5", "no.5", "si eau", "delina", "baccarat rouge 540 extrait"]
MEN = ["men", "man", "for him", "pour homme", "homme", "uomo", "male", "sauvage", "bleu de chanel",
       "aventus", "eros", "1 million", "invictus", "acqua di gio", "y eau de", "y le parfum", "spicebomb",
       "bad boy", "explorer", "wanted", "terre d'hermes", "l'homme", "layton", "oud for greatness",
       "interlude man", "born in roma", "luna rossa", "the one eau de parfum", "allure homme"]
UNISEX = ["unisex", "for all", "gender neutral"]

DEFAULT_NICHE = ["creed", "parfums de marly", "maison francis kurkdjian", "xerjoff", "initio", "amouage",
                 "kilian", "byredo", "le labo", "tom ford private blend", "nishane", "roja", "frederic malle",
                 "diptyque", "jo malone", "penhaligon's", "mancera", "montale", "maison margiela",
                 "memo paris", "clive christian", "bdk", "ormonde jayne", "serge lutens", "acqua di parma",
                 "tom ford", "maison crivelli", "vilhelm parfumerie", "goldfield & banks", "electimuss"]


def _has(text, words):
    return any(re.search(rf"(?<![a-z]){re.escape(w.strip())}(?![a-z])", text) for w in words)


def gender(name, category):
    cat = f" {category.lower()} "
    if _has(cat, ["unisex"]):
        return "unisex"
    if _has(cat, ["women", "women's", "womens", "ladies", "her", "female"]):
        return "women"
    if _has(cat, ["men", "men's", "mens", "him", "male"]):
        return "men"
    text = f" {name.lower()} "
    if _has(text, UNISEX):
        return "unisex"
    w, m = _has(text, WOMEN), _has(text, MEN)
    if w and not m:
        return "women"
    if m and not w:
        return "men"
    return "unisex"


def is_niche(brand, niche_brands=None):
    b = brand.lower().strip()
    return any(b == n or b.startswith(n) for n in (niche_brands or DEFAULT_NICHE))


def size_ml(name):
    m = re.search(r"(\d{2,4})\s?ml", name.lower())
    return int(m.group(1)) if m else None


GENDER_LABEL = {"men": "For him", "women": "For her", "unisex": "Unisex"}


def concentration(name):
    n = name.lower()
    for key, label in [("extrait", "Extrait"), ("elixir", "Elixir"), ("eau de parfum", "Eau de Parfum"),
                       ("edp", "Eau de Parfum"), ("eau de toilette", "Eau de Toilette"), ("edt", "Eau de Toilette"),
                       ("cologne", "Cologne"), ("parfum", "Parfum"), ("mist", "Body Mist")]:
        if key in n:
            return label
    return ""


_STRIP = r"\b(eau de parfum|eau de toilette|eau de cologne|extrait de parfum|edp|edt|perfume mist|\d+\s?ml)\b"


def base_key(brand, name):
    """'Dior', 'Sauvage Eau de Parfum 100ml' -> 'dior|sauvage'. Used to match scent notes."""
    n = re.sub(_STRIP, "", (name or "").lower())
    n = re.sub(r"\b(spray|vaporisateur|for men|for women|pour homme|pour femme)\b$", "", n.strip())
    n = re.sub(r"\s+", " ", n).strip(" -,")
    if n.endswith(" cologne"):
        n = n[: -len(" cologne")]
    return f"{(brand or '').lower().strip()}|{n}"


def verdict(price, pts, day):
    """Buy now / Fair / Wait, from where today's price sits in this listing's own history."""
    import statistics
    past = [p for d, p in pts if d < day]
    if len(past) < 10:
        return {"k": "track", "label": "Tracking", "why": "We need a few more weeks of prices before we can judge this one."}
    lo, med = min(past), statistics.median(past)
    if price <= lo + 0.01 and price < med * 0.97:
        return {"k": "buy", "label": "Buy now", "why": f"Lowest price we've tracked. Usually £{med:.2f}."}
    if price <= med * 0.93:
        return {"k": "buy", "label": "Good time to buy", "why": f"{round((med - price) / med * 100)}% below its usual £{med:.2f}."}
    if price <= med * 1.02:
        return {"k": "fair", "label": "Fair price", "why": f"About what it usually costs (£{med:.2f}). No rush."}
    return {"k": "wait", "label": "Wait", "why": f"Above its usual £{med:.2f}. It has been as low as £{lo:.2f}."}


def tag(product, niche_brands=None):
    """Add gender, niche and size keys to a product dict (in place) and return it."""
    product["gender"] = gender(product.get("name", ""), product.get("category", "") or "")
    product["gender_label"] = GENDER_LABEL[product["gender"]]
    product["niche"] = is_niche(product.get("brand", ""), niche_brands)
    product["ml"] = size_ml(product.get("name", ""))
    product["conc"] = concentration(product.get("name", ""))
    product["shape"] = sum(map(ord, product.get("name", ""))) % 3
    return product
