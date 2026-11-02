# The Ledger: rules for Claude

UK designer and niche fragrance price-drop tracker. Live at https://theledgeruk.co.uk (GitHub Pages, built by `.github/workflows/daily.yml` at 06:17 UK time).

## Hard rules
- Never show fabricated prices, retailers, reviews or stats on the live site. Demo data (`python run.py --demo`) stays out of production output.
- Only retailers in `merchants_allow` appear. Every buy link must be a real affiliate link.
- Keep the ad disclosure in the footer and the `#ad` tag on social captions. UK law requires them.
- No scraping or unofficial price sources. Data comes only from official affiliate feeds.
- Secrets live in GitHub repo secrets and are referenced as `${ENV_VAR}` in `config.yaml`. Never commit keys.

## Where things live
- `config.yaml`: all settings, feeds and allowlists. Change behaviour here before touching code.
- `engine/`: parsing, classification, rendering, social cards and video.
- `run.py`: daily entry point. `post_*.py`: social posting.
- `templates/`, `static/`: site templates and assets.
- `tests/`: pytest suite.

## Affiliate status (Nov 2026)
- Awin closed the account on 21 Oct 2026. Final. Its parser stays for Awin-format feeds.
- Rakuten Advertising: publisher account created 2 Nov 2026 (SID 4771128). The Fragrance Shop (MID 43488, 2% CPS, 30-day cookie) needs manual approval. Once approved, set the `RAKUTEN_FEED_URL` secret.
- Amazon Associates UK is the interim route. Tag `theledgeruk-21`, set in `config.yaml` on 2 Nov 2026. Needs 3 qualifying sales for account review.

## Working method
1. Read the relevant code before changing it.
2. Run `pytest` before every commit. Add a test for every bug fixed.
3. Run `python run.py --demo` and check `output/site/index.html` for template changes.
4. Small commits with clear messages. Never force-push `main`.
5. Treat any change to `.github/workflows/` as high risk. It controls the live daily run.
