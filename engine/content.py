"""Build trust pages and guides from Markdown files in content/."""
import glob
import json
import os

import markdown

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path):
    """Read a content file: 'title:' and 'description:' lines, a blank line, then Markdown."""
    with open(path, encoding="utf-8") as fh:
        head, _, body = fh.read().partition("\n\n")
    meta = dict(line.split(":", 1) for line in head.splitlines() if ":" in line)
    return {
        "slug": os.path.splitext(os.path.basename(path))[0],
        "title": meta.get("title", "").strip(),
        "description": meta.get("description", "").strip(),
        "body": body,
    }


def load_guides():
    return [_load(p) for p in sorted(glob.glob(os.path.join(HERE, "content", "guides", "*.md")))]


def build_content(env, common, cfg, out_dir, write):
    """Write content pages and guides. Returns the list of URLs created, for the sitemap."""
    site = cfg["site"]
    email = site.get("contact_email") or ""
    contact = (f'<a href="mailto:{email}">{email}</a>' if email
               else "Our contact inbox is being set up. Please check back shortly.")
    tpl = env.get_template("page.html")
    urls = []

    for path in sorted(glob.glob(os.path.join(HERE, "content", "pages", "*.md"))):
        page = _load(path)
        html = markdown.markdown(page["body"]).replace("{{CONTACT_EMAIL}}", contact)
        write(os.path.join(out_dir, f"{page['slug']}.html"),
              tpl.render(**common, root="", page=page, html=html, canon=f"{page['slug']}.html",
                         jsonld=None))
        urls.append(f"{page['slug']}.html")

    guides = load_guides()
    for i, g in enumerate(guides):
        related = [guides[(i + k) % len(guides)] for k in range(1, min(4, len(guides)))]
        base = site["base_url"].rstrip("/")
        org = {"@type": "Organization", "name": site["name"], "url": f"{base}/", "logo": f"{base}/logo.png"}
        jsonld = json.dumps({
            "@context": "https://schema.org", "@type": "Article",
            "headline": g["title"], "description": g["description"],
            "url": f"{base}/guides/{g['slug']}.html", "image": f"{base}/og.png",
            "author": org, "publisher": org,
        }).replace("</", "<\\/")
        write(os.path.join(out_dir, "guides", f"{g['slug']}.html"),
              tpl.render(**common, root="../", page=g, html=markdown.markdown(g["body"]),
                         canon=f"guides/{g['slug']}.html", jsonld=jsonld, related=related))
        urls.append(f"guides/{g['slug']}.html")

    index = "".join(
        f'<a class="guide" href="guides/{g["slug"]}.html"><h2>{g["title"]}</h2><p>{g["description"]}</p></a>'
        for g in guides)
    write(os.path.join(out_dir, "guides.html"), tpl.render(
        **common, root="", canon="guides.html", jsonld=None,
        page={"title": "Fragrance buying guides",
              "description": "Practical guides to buying designer and niche fragrance at the right price in the UK."},
        html=f'<div class="guides">{index}</div>'))
    urls.append("guides.html")
    urls += build_popular(tpl, common, cfg, out_dir, write)
    return urls


def amazon_link(brand, name, tag):
    """Amazon UK search link with our Associates tag. Search links never go stale."""
    from urllib.parse import quote_plus
    return f"https://www.amazon.co.uk/s?k={quote_plus(f'{brand} {name}')}&tag={quote_plus(tag)}"


def build_popular(tpl, common, cfg, out_dir, write):
    """'Popular fragrances' page with Amazon links. Only built when an Associates tag is set."""
    from html import escape
    amz = cfg.get("amazon") or {}
    tag, picks = amz.get("tag"), amz.get("picks") or []
    if not tag or not picks:
        return []
    parts = ["<p>The designer fragrances UK buyers search for most. We don't show a price here because "
             "we only publish prices we have tracked ourselves. Check today's price on Amazon, and for the "
             "safest purchase choose listings <em>dispatched from and sold by Amazon</em>. See our guide to "
             '<a href="guides/avoid-fake-fragrances-online.html">avoiding fake fragrances online</a>.</p>']
    for group, heading in (("Men", "For him"), ("Women", "For her")):
        items = [x for x in picks if x.get("g") == group]
        if not items:
            continue
        parts.append(f'<h2>{heading}</h2><ul class="picks">')
        for x in items:
            parts.append(f'<li><span><b>{escape(x["brand"])}</b> {escape(x["name"])}</span> '
                         f'<a href="{escape(amazon_link(x["brand"], x["name"], tag))}" '
                         f'rel="sponsored nofollow noopener" target="_blank">Check price on Amazon</a></li>')
        parts.append("</ul>")
    page = {"title": "Popular designer fragrances in the UK",
            "description": "The designer perfumes and aftershaves UK buyers search for most, with links to check today's price."}
    write(os.path.join(out_dir, "popular.html"),
          tpl.render(**common, root="", page=page, html="".join(parts), canon="popular.html", jsonld=None))
    return ["popular.html"]
