"""On-page SEO signals (master context §8, SEO row)."""

from app.core.enums import EvidenceType
from app.intelligence.html import json_ld, ld_types, meta
from app.intelligence.types import Area, Observation, Page, SiteContext, outer

TITLE_RANGE = (15, 65)
DESCRIPTION_RANGE = (50, 165)


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    out: list[Observation] = []

    def obs(key: str, value: object, page: Page, text: str, **kw: object) -> None:
        out.append(Observation(Area.SEO, f"seo.{key}", value, page.url, text, **kw))  # type: ignore[arg-type]

    title_node = home.tree.css_first("title")
    title = " ".join((title_node.text() if title_node else "").split())
    if title:
        obs(
            "home_title",
            {
                "text": title,
                "length": len(title),
                "in_range": TITLE_RANGE[0] <= len(title) <= TITLE_RANGE[1],
            },
            home,
            f"<title>{title}</title>",
        )
    else:
        obs("home_title", None, home, "The homepage has no <title>", confidence=0.95)

    description = meta(home, "description")
    if description:
        obs(
            "home_meta_description",
            {
                "text": description,
                "length": len(description),
                "in_range": DESCRIPTION_RANGE[0] <= len(description) <= DESCRIPTION_RANGE[1],
            },
            home,
            f'<meta name="description" content="{description[:200]}">',
        )
    else:
        obs(
            "home_meta_description",
            None,
            home,
            "The homepage has no meta description",
            confidence=0.95,
        )

    no_title = [p.url for p in pages if not _title(p)]
    no_description = [p.url for p in pages if not meta(p, "description")]
    no_h1 = [p.url for p in pages if not p.tree.css("h1")]
    many_h1 = [p.url for p in pages if len(p.tree.css("h1")) > 1]
    checked = [p.url for p in pages]
    for key, urls, what in (
        ("pages_missing_title", no_title, "no <title>"),
        ("pages_missing_meta_description", no_description, "no meta description"),
        ("pages_without_h1", no_h1, "no <h1>"),
        ("pages_with_multiple_h1", many_h1, "more than one <h1>"),
    ):
        if urls:
            out.append(
                Observation(
                    Area.SEO,
                    f"seo.{key}",
                    urls,
                    urls[0],
                    f"{len(urls)} of {len(checked)} crawled pages have {what}: "
                    f"{', '.join(urls[:3])}",
                    confidence=0.9,
                    seen_on=urls,
                )
            )

    h1s = home.tree.css("h1")
    obs(
        "home_h1",
        " ".join((h1s[0].text() or "").split())[:200] if h1s else None,
        home,
        outer(h1s[0]) if h1s else "The homepage has no <h1>",
        confidence=0.9,
    )

    canonical = home.tree.css_first('link[rel="canonical"][href]')
    obs(
        "home_canonical",
        canonical.attributes.get("href") if canonical else None,
        home,
        outer(canonical) if canonical else "No canonical link on the homepage",
        confidence=0.9,
    )

    types: list[str] = []
    type_page: Page | None = None
    for page in pages:
        for item in json_ld(page):
            for t in ld_types(item):
                if t not in types:
                    types.append(t)
                    type_page = type_page or page
    if types and type_page is not None:
        obs(
            "structured_data_types",
            types,
            type_page,
            f"JSON-LD types found: {', '.join(types[:8])}",
            evidence_type=EvidenceType.STRUCTURED_DATA,
            confidence=0.95,
        )
    else:
        obs(
            "structured_data_types",
            [],
            home,
            f"No JSON-LD structured data on {len(pages)} crawled pages",
            evidence_type=EvidenceType.STRUCTURED_DATA,
            confidence=0.8,
            seen_on=checked,
        )

    og_title = meta(home, "og:title")
    obs(
        "open_graph",
        og_title is not None,
        home,
        f'<meta property="og:title" content="{og_title}">'
        if og_title
        else "No Open Graph tags on the homepage",
        confidence=0.9,
    )

    noindex = [
        p.url
        for p in pages
        if "noindex" in (meta(p, "robots") or "").lower()
        or "noindex" in p.headers.get("x-robots-tag", "").lower()
    ]
    if noindex:
        out.append(
            Observation(
                Area.SEO,
                "seo.noindex_pages",
                noindex,
                noindex[0],
                f"Marked noindex: {', '.join(noindex[:3])}",
                confidence=0.95,
                seen_on=noindex,
            )
        )

    images = [img for p in pages for img in p.tree.css("img")]
    if images:
        with_alt = sum(1 for img in images if (img.attributes.get("alt") or "").strip())
        obs(
            "image_alt_coverage",
            {
                "images": len(images),
                "with_alt": with_alt,
                "ratio": round(with_alt / len(images), 2),
            },
            home,
            f"{with_alt} of {len(images)} images on crawled pages have alt text",
            confidence=0.9,
        )

    words = len(home.text.split())
    obs(
        "home_word_count",
        words,
        home,
        f"The homepage has about {words} words of visible text",
        confidence=0.85,
    )

    langs = sorted(
        {
            (n.attributes.get("hreflang") or "")
            for p in pages
            for n in p.tree.css('link[rel="alternate"][hreflang]')
        }
        - {""}
    )
    if langs:
        obs("hreflang", langs, home, f"hreflang alternates: {', '.join(langs)}", confidence=0.95)
    return out


def _title(page: Page) -> str:
    node = page.tree.css_first("title")
    return " ".join((node.text() if node else "").split())
