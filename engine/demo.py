"""Generate 31 days of sample Awin-format feeds so the pipeline can be tested
before any affiliate account exists. Prices are invented. Retailers are fictional."""
import csv
import os
import random
from datetime import date, timedelta

PRODUCTS = [
    ("Dior", "Sauvage Eau de Parfum 100ml", 115), ("Chanel", "Bleu de Chanel Eau de Parfum 100ml", 128),
    ("Creed", "Aventus Eau de Parfum 100ml", 330), ("Tom Ford", "Oud Wood Eau de Parfum 50ml", 205),
    ("Yves Saint Laurent", "Y Eau de Parfum 100ml", 108), ("Giorgio Armani", "Acqua di Gio Profondo 75ml", 92),
    ("Jean Paul Gaultier", "Le Male Elixir 125ml", 105), ("Parfums de Marly", "Layton Eau de Parfum 125ml", 255),
    ("Maison Francis Kurkdjian", "Baccarat Rouge 540 Eau de Parfum 70ml", 245), ("Xerjoff", "Naxos Eau de Parfum 100ml", 215),
    ("Valentino", "Uomo Born in Roma Intense 100ml", 99), ("Prada", "Luna Rossa Ocean Eau de Parfum 100ml", 104),
    ("Versace", "Eros Flame Eau de Parfum 100ml", 82), ("Dolce & Gabbana", "The One Eau de Parfum 100ml", 89),
    ("Hermes", "Terre d'Hermes Eau de Toilette 100ml", 112), ("Guerlain", "L'Homme Ideal Eau de Parfum 100ml", 98),
    ("Initio", "Oud for Greatness Eau de Parfum 90ml", 260), ("Amouage", "Interlude Man Eau de Parfum 100ml", 290),
    ("Kilian", "Angels' Share Eau de Parfum 50ml", 225), ("Byredo", "Gypsy Water Eau de Parfum 100ml", 190),
    ("Le Labo", "Santal 33 Eau de Parfum 50ml", 195), ("Viktor & Rolf", "Spicebomb Extreme 90ml", 96),
    ("Paco Rabanne", "1 Million Elixir 100ml", 94), ("Carolina Herrera", "Bad Boy Cobalt 100ml", 88),
    ("Montblanc", "Explorer Eau de Parfum 100ml", 74), ("Azzaro", "The Most Wanted Parfum 100ml", 90),
    ("Lancome", "La Vie Est Belle Eau de Parfum 100ml", 118), ("Chanel", "Coco Mademoiselle Eau de Parfum 100ml", 138),
    ("Dior", "Miss Dior Eau de Parfum 100ml", 132), ("Gucci", "Bloom Eau de Parfum 100ml", 115),
]
MERCHANTS = [("1001", "Demo Retailer A", 1.00), ("1002", "Demo Retailer B", 0.97), ("1003", "Demo Retailer C", 1.03)]
FIELDS = ["aw_product_id", "merchant_id", "merchant_name", "product_name", "brand_name", "category_name",
          "search_price", "rrp_price", "aw_deep_link", "merchant_image_url", "in_stock", "currency"]


def build(out_dir, end_day=None, days=31, seed=7):
    random.seed(seed)
    end_day = end_day or date.today()
    os.makedirs(out_dir, exist_ok=True)
    # Each (product, merchant) gets a few planned sale windows
    sales = {}
    for i in range(len(PRODUCTS)):
        for mid, _, _ in MERCHANTS:
            windows = []
            if random.random() < 0.45:
                start = random.randint(3, days - 2)
                windows.append((start, start + random.randint(2, 6), random.uniform(0.12, 0.35)))
            sales[(i, mid)] = windows
    paths = []
    for d in range(days):
        day = end_day - timedelta(days=days - 1 - d)
        rows = []
        for i, (brand, name, rrp) in enumerate(PRODUCTS):
            for mid, mname, factor in MERCHANTS:
                if (i + int(mid)) % 3 == 0:
                    continue  # not every retailer stocks everything
                base = rrp * factor * random.uniform(0.98, 1.0)
                for start, stop, cut in sales[(i, mid)]:
                    if start <= d <= stop:
                        base = rrp * factor * (1 - cut)
                if d == days - 1 and (i * 7 + int(mid)) % 5 == 0:
                    base = rrp * factor * 0.74  # guarantee drops on the final day
                rows.append({
                    "aw_product_id": f"{i:04d}", "merchant_id": mid, "merchant_name": mname,
                    "product_name": name, "brand_name": brand, "category_name": "Fragrance",
                    "search_price": f"{base:.2f}", "rrp_price": f"{rrp:.2f}",
                    "aw_deep_link": "#demo-link", "merchant_image_url": "",
                    "in_stock": "1", "currency": "GBP",
                })
        path = os.path.join(out_dir, f"feed_{day.isoformat()}.csv")
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        paths.append((day.isoformat(), path))
    return paths
