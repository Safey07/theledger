"""Generate 31 days of sample Awin-format feeds so the pipeline can be tested
before any affiliate account exists. Prices are invented. Retailers are fictional."""
import csv
import os
import random
from datetime import date, timedelta

M, W, U = "Men's Fragrance", "Women's Fragrance", "Unisex Fragrance"
PRODUCTS = [
    # Men's designer
    ("Dior", "Sauvage Eau de Parfum 100ml", 115, M), ("Dior", "Sauvage Elixir 60ml", 135, M),
    ("Dior", "Homme Intense 100ml", 118, M), ("Chanel", "Bleu de Chanel Eau de Parfum 100ml", 128, M),
    ("Chanel", "Allure Homme Sport Eau de Toilette 100ml", 112, M), ("Yves Saint Laurent", "Y Eau de Parfum 100ml", 108, M),
    ("Yves Saint Laurent", "La Nuit de L'Homme Eau de Toilette 100ml", 92, M), ("Yves Saint Laurent", "MYSLF Eau de Parfum 100ml", 115, M),
    ("Giorgio Armani", "Acqua di Gio Profondo 75ml", 92, M), ("Giorgio Armani", "Stronger With You Intensely 100ml", 98, M),
    ("Giorgio Armani", "Code Parfum 75ml", 105, M), ("Jean Paul Gaultier", "Le Male Elixir 125ml", 105, M),
    ("Jean Paul Gaultier", "Le Beau Le Parfum 125ml", 99, M), ("Jean Paul Gaultier", "Ultra Male Eau de Toilette 125ml", 88, M),
    ("Valentino", "Uomo Born in Roma Intense 100ml", 99, M), ("Prada", "Luna Rossa Ocean Eau de Parfum 100ml", 104, M),
    ("Prada", "L'Homme Eau de Toilette 100ml", 98, M), ("Versace", "Eros Flame Eau de Parfum 100ml", 82, M),
    ("Versace", "Eros Eau de Parfum 100ml", 86, M), ("Versace", "Dylan Blue Pour Homme 100ml", 72, M),
    ("Dolce & Gabbana", "The One for Men Eau de Parfum 100ml", 89, M), ("Dolce & Gabbana", "Light Blue Pour Homme 125ml", 78, M),
    ("Hermes", "Terre d'Hermes Eau de Toilette 100ml", 112, M), ("Hermes", "H24 Eau de Parfum 100ml", 118, M),
    ("Guerlain", "L'Homme Ideal Eau de Parfum 100ml", 98, M), ("Viktor & Rolf", "Spicebomb Extreme 90ml", 96, M),
    ("Paco Rabanne", "1 Million Elixir 100ml", 94, M), ("Paco Rabanne", "Phantom Eau de Toilette 100ml", 84, M),
    ("Paco Rabanne", "Invictus Victory Elixir 100ml", 92, M), ("Carolina Herrera", "Bad Boy Cobalt 100ml", 88, M),
    ("Montblanc", "Explorer Eau de Parfum 100ml", 74, M), ("Montblanc", "Legend Eau de Parfum 100ml", 66, M),
    ("Azzaro", "The Most Wanted Parfum 100ml", 90, M), ("Azzaro", "Wanted by Night 100ml", 80, M),
    ("Hugo Boss", "Boss Bottled Elixir 100ml", 92, M), ("Hugo Boss", "Boss Bottled Eau de Parfum 100ml", 82, M),
    ("Givenchy", "Gentleman Reserve Privee 100ml", 98, M), ("Burberry", "Hero Eau de Parfum 100ml", 98, M),
    ("Ralph Lauren", "Polo Red Eau de Parfum 125ml", 86, M), ("Calvin Klein", "Eternity for Men Eau de Parfum 100ml", 68, M),
    ("Bvlgari", "Man in Black Eau de Parfum 100ml", 98, M), ("Mugler", "Alien Man Eau de Toilette 100ml", 88, M),
    # Women's designer
    ("Chanel", "Coco Mademoiselle Eau de Parfum 100ml", 138, W), ("Chanel", "Chance Eau Tendre Eau de Parfum 100ml", 132, W),
    ("Chanel", "N°5 Eau de Parfum 100ml", 152, W), ("Dior", "Miss Dior Eau de Parfum 100ml", 132, W),
    ("Dior", "J'adore Eau de Parfum 100ml", 135, W), ("Lancome", "La Vie Est Belle Eau de Parfum 100ml", 118, W),
    ("Lancome", "Idole Eau de Parfum 100ml", 110, W), ("Gucci", "Bloom Eau de Parfum 100ml", 115, W),
    ("Gucci", "Flora Gorgeous Gardenia Eau de Parfum 100ml", 118, W), ("Yves Saint Laurent", "Libre Eau de Parfum 90ml", 128, W),
    ("Yves Saint Laurent", "Black Opium Eau de Parfum 90ml", 118, W), ("Carolina Herrera", "Good Girl Eau de Parfum 80ml", 112, W),
    ("Giorgio Armani", "My Way Eau de Parfum 90ml", 110, W), ("Giorgio Armani", "Si Eau de Parfum 100ml", 108, W),
    ("Viktor & Rolf", "Flowerbomb Eau de Parfum 100ml", 130, W), ("Mugler", "Alien Eau de Parfum 90ml", 120, W),
    ("Paco Rabanne", "Fame Parfum 80ml", 104, W), ("Valentino", "Donna Born in Roma Eau de Parfum 100ml", 118, W),
    ("Prada", "Paradoxe Eau de Parfum 90ml", 122, W), ("Marc Jacobs", "Daisy Eau de Toilette 100ml", 92, W),
    ("Burberry", "Goddess Eau de Parfum 100ml", 118, W), ("Givenchy", "L'Interdit Eau de Parfum 80ml", 108, W),
    ("Dolce & Gabbana", "Light Blue Eau de Toilette 100ml", 82, W), ("Jean Paul Gaultier", "Scandal Eau de Parfum 80ml", 96, W),
    ("Narciso Rodriguez", "For Her Eau de Parfum 100ml", 108, W), ("Chloe", "Eau de Parfum 75ml", 112, W),
    ("Ariana Grande", "Cloud Eau de Parfum 100ml", 52, W), ("Billie Eilish", "Eilish Eau de Parfum 100ml", 58, W),
    ("Sol de Janeiro", "Cheirosa 62 Perfume Mist 240ml", 38, W), ("Kayali", "Vanilla 28 Eau de Parfum 50ml", 82, W),
    # Niche and unisex
    ("Creed", "Aventus Eau de Parfum 100ml", 330, M), ("Creed", "Silver Mountain Water 100ml", 285, U),
    ("Parfums de Marly", "Layton Eau de Parfum 125ml", 255, M), ("Parfums de Marly", "Delina Eau de Parfum 75ml", 245, W),
    ("Maison Francis Kurkdjian", "Baccarat Rouge 540 Eau de Parfum 70ml", 245, U),
    ("Maison Francis Kurkdjian", "Grand Soir Eau de Parfum 70ml", 210, U),
    ("Xerjoff", "Naxos Eau de Parfum 100ml", 215, U), ("Xerjoff", "Erba Pura Eau de Parfum 100ml", 190, U),
    ("Initio", "Oud for Greatness Eau de Parfum 90ml", 260, U), ("Amouage", "Interlude Man Eau de Parfum 100ml", 290, M),
    ("Amouage", "Reflection Man Eau de Parfum 100ml", 255, M), ("Kilian", "Angels' Share Eau de Parfum 50ml", 225, U),
    ("Byredo", "Gypsy Water Eau de Parfum 100ml", 190, U), ("Byredo", "Mojave Ghost Eau de Parfum 100ml", 190, U),
    ("Le Labo", "Santal 33 Eau de Parfum 50ml", 195, U), ("Le Labo", "Another 13 Eau de Parfum 50ml", 195, U),
    ("Tom Ford", "Oud Wood Eau de Parfum 50ml", 205, U), ("Tom Ford", "Tobacco Vanille Eau de Parfum 50ml", 205, U),
    ("Tom Ford", "Ombre Leather Eau de Parfum 100ml", 165, U), ("Jo Malone", "Wood Sage & Sea Salt Cologne 100ml", 118, U),
    ("Jo Malone", "English Pear & Freesia Cologne 100ml", 118, W), ("Diptyque", "Philosykos Eau de Parfum 75ml", 150, U),
    ("Maison Margiela", "Replica Jazz Club Eau de Toilette 100ml", 128, M), ("Maison Margiela", "Replica By the Fireplace 100ml", 128, U),
    ("Nishane", "Hacivat Extrait de Parfum 50ml", 185, U), ("Mancera", "Cedrat Boise Eau de Parfum 120ml", 125, U),
    ("Montale", "Arabians Tonka Eau de Parfum 100ml", 115, U), ("Acqua di Parma", "Colonia Eau de Cologne 100ml", 128, U),
    ("Penhaligon's", "Halfeti Eau de Parfum 100ml", 210, U), ("Memo Paris", "African Leather Eau de Parfum 75ml", 215, U),
]
MERCHANTS = [("1001", "Demo Retailer A", 1.00), ("1002", "Demo Retailer B", 0.97), ("1003", "Demo Retailer C", 1.03),
             ("1004", "Demo Retailer D", 0.99)]
FIELDS = ["aw_product_id", "merchant_id", "merchant_name", "product_name", "brand_name", "category_name",
          "search_price", "rrp_price", "aw_deep_link", "merchant_image_url", "in_stock", "currency"]


def build(out_dir, end_day=None, days=31, seed=7):
    random.seed(seed)
    end_day = end_day or date.today()
    os.makedirs(out_dir, exist_ok=True)
    sales = {}
    for i in range(len(PRODUCTS)):
        for mid, _, _ in MERCHANTS:
            windows = []
            if random.random() < 0.4:
                start = random.randint(3, days - 3)
                windows.append((start, start + random.randint(2, 6), random.uniform(0.10, 0.32)))
            sales[(i, mid)] = windows
    # A varied set of genuine-looking drops on the final day
    final_cuts = {}
    for i in range(len(PRODUCTS)):
        if random.random() < 0.22:
            mid = random.choice(MERCHANTS)[0]
            final_cuts[(i, mid)] = random.choice([0.11, 0.13, 0.15, 0.17, 0.19, 0.22, 0.24, 0.28, 0.31, 0.36])
    paths = []
    for d in range(days):
        day = end_day - timedelta(days=days - 1 - d)
        rows = []
        for i, (brand, name, rrp, cat) in enumerate(PRODUCTS):
            for mid, mname, factor in MERCHANTS:
                if (i + int(mid)) % 4 == 0:
                    continue  # not every retailer stocks everything
                base = rrp * factor * random.uniform(0.97, 1.0)
                for start, stop, cut in sales[(i, mid)]:
                    if start <= d <= stop:
                        base = rrp * factor * (1 - cut)
                if d == days - 1 and (i, mid) in final_cuts:
                    base = rrp * factor * (1 - final_cuts[(i, mid)])
                rows.append({
                    "aw_product_id": f"{i:04d}", "merchant_id": mid, "merchant_name": mname,
                    "product_name": name, "brand_name": brand, "category_name": cat,
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
