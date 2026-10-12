"""Slice 6.2: comparing a page with the last copy kept."""

from datetime import UTC, datetime

from app.intelligence.types import Page
from app.monitoring.website import Reread, Snapshot, compare, home_links, text_change

SEEN = datetime(2026, 10, 1, tzinfo=UTC)


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def reread(*pairs: tuple[str, str | None, str, str]) -> Reread:
    """(url, category, html before, html now) per page read again."""
    return Reread(
        pages=[
            (Snapshot(url, cat, old, SEEN), Page(url=url, html=new, category=cat))
            for url, cat, old, new in pairs
        ]
    )


def test_the_same_words_are_not_a_change() -> None:
    assert text_change("Fixed  fees\nfor visas", "Fixed fees for visas") is None


def test_nearby_edits_are_one_passage_far_ones_are_two() -> None:
    words = " ".join(f"w{i}" for i in range(60))
    near = words.replace("w10", "x10").replace("w14", "x14")
    before, after, passages = text_change(words, near)  # type: ignore[misc]
    assert passages == 1 and "w10" in before and "x14" in after
    far = words.replace("w5", "x5").replace("w50", "x50")
    assert text_change(words, far)[2] == 2  # type: ignore[index]


def test_markup_only_changes_are_not_changes() -> None:
    old = page("<p>Spouse visas</p>")
    new = page('<div class="new"><p>Spouse   visas</p></div>', "<script>var t=1</script>")
    assert compare(reread(("https://a.test/", "home", old, new))) == []


def test_home_links_keep_only_the_sites_own_known_kinds_of_page() -> None:
    html = page(
        '<a href="/pricing">Pricing</a><a href="/blog/a-post">A post</a>'
        '<a href="https://other.test/contact">Contact</a><a href="/brochure.pdf">Services</a>'
    )
    assert home_links(html, "https://a.test/") == {"https://a.test/pricing": "Pricing"}


def test_technology_and_contact_routes_are_compared_on_the_same_pages() -> None:
    old = page('<a href="tel:+441610000000">Call</a>')
    new = page(
        '<a href="mailto:hello@a.test">Email</a>',
        '<script src="https://js.stripe.com/v3/"></script>',
    )
    titles = {c.title: c for c in compare(reread(("https://a.test/", None, old, new)))}
    assert "Technology added: Stripe" in titles
    assert "Email address added: hello@a.test" in titles
    removed = titles["Phone number removed: +441610000000"]
    assert removed.topic == "contact" and "tel" in (removed.before or "")
    assert removed.before_seen_at == SEEN


def test_a_page_that_is_gone_is_removed_with_what_it_said() -> None:
    snap = Snapshot("https://a.test/pricing", "pricing", page("<p>From £500</p>"), SEEN)
    (change,) = compare(Reread(gone=[(snap, 410)]))
    assert change.title == "Pricing page removed (now answers 410)"
    assert change.topic == "pricing" and change.before == "From £500"
