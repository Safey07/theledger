# The Ledger

Automated fragrance price-drop tracker. Every morning it pulls retailer product feeds, finds fragrances selling well below their own 30-day price, and then:

1. Rebuilds a static website (today's drops, a page per product with price history, a page per brand, sitemap).
2. Writes and sends a morning email digest.
3. Generates 3 portrait image cards with captions for TikTok and Instagram.

Every buy link is an affiliate link. You earn commission on sales.

**Why fragrance:** frequent discounts, repeat purchases, high basket values, strong search demand ("Aventus cheapest UK"), and sneakers are already crowded with big trackers. Gulf demand for fragrance also gives a clear second market.

## Try it now (no accounts)

```
pip install -r requirements.txt
python run.py --demo
```

Open `output/site/index.html`. Demo data is invented.

## Go live: your one-time setup (about 2 to 3 hours plus approval waits)

| # | Step | Where |
|---|------|-------|
| 1 | Create a free GitHub account and a new **public** repo called `theledger`. Upload this folder. | github.com |
| 2 | Settings → Pages → Source: **GitHub Actions**. | repo settings |
| 3 | Edit `config.yaml`. Set `base_url` to `https://YOURNAME.github.io/theledger`. | this repo |
| 4 | Apply to Awin as a publisher. Use the live site URL from step 2. | awin.com |
| 5 | Inside Awin, join fragrance advertisers (search "fragrance", "perfume", "beauty"). Aim for 10+ approvals. | Awin dashboard |
| 6 | Awin → Toolbox → Create-a-Feed. Select approved advertisers, CSV, gzip. Copy the feed URL. | Awin dashboard |
| 7 | Repo → Settings → Secrets → Actions. Add `AWIN_FEED_URL`. | repo settings |
| 8 | Create a free Buttondown account. Add secret `BUTTONDOWN_API_KEY`. Copy its embed form action URL into secret `SIGNUP_FORM_ACTION`. Set `email.provider: "buttondown"` in config. | buttondown.com |
| 9 | Actions tab → Daily run → Run workflow. Check the site. | repo |
| 10 | Submit `sitemap.xml` to Google Search Console. | search.google.com/search-console |

After step 9 it runs itself every morning at 06:17 UK time.

Notes
- Awin publisher sign-up may ask for a small refundable deposit. Check their current terms.
- Verify the Buttondown API call in `run.py` against their current docs before going live.
- UK law requires clear ad disclosure. The site footer and `#ad` caption tag already cover this. Keep them.

## Daily cost
£0 on GitHub's free tier. A custom domain (~£10/yr) helps trust and SEO. Point it at GitHub Pages and update `base_url`.

## Your weekly 15 minutes
- Download the `social-cards` artifact from the latest Actions run. Schedule the week's cards in Buffer or Later.
- Glance at Awin for advertisers who left or new ones to join.

## Scale plan

| Stage | Trigger | Move |
|-------|---------|------|
| 1 | Live | Run 60 days. Let Google index product pages. Post cards daily. |
| 2 | 1,000 email subscribers or steady Google traffic | Add more networks (Rakuten, Impact, Partnerize) as extra entries in `feeds:`. More retailers means more drops and better price comparison. |
| 3 | Clicks converting | Add "price alert for this item" buttons. Personal alerts convert best. |
| 4 | UK proven | Gulf edition. Gulf retailers run affiliate programs through regional networks. Copy config, set currency to AED/SAR, add Arabic templates. |
| 5 | Traffic compounding | Sell a sponsored slot in the email to fragrance brands. Paid newsletter tier with early access to drops. |

## How it works

```
config.yaml          all settings
run.py               the daily job
engine/data.py       feed parsing, price history (SQLite), drop detection
engine/render.py     website, email, social cards
engine/demo.py       invented sample feeds for testing
templates/           site HTML
.github/workflows/   the daily schedule and deploy
```

A drop is published when an in-stock item is at least 10% and £5 below its own 30-day median, and that price has not already been announced this month. Tune these in `config.yaml`.
