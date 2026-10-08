"""How a visitor becomes an enquiry (master context §8, Conversion row)."""

import re
from typing import Any

from app.intelligence.html import links, script_sources
from app.intelligence.types import Area, Observation, Page, SiteContext, excerpt, outer

CTA = re.compile(
    r"\b(book (?:a |an |your )?(?:call|demo|consultation|meeting|appointment)|schedule|get started|"
    r"start (?:now|free|your)|free trial|request (?:a )?(?:quote|demo|callback)|"
    r"get (?:a |your )?quote|"
    r"contact us|talk to|speak to|get in touch|sign up|apply now|enquire|book now)\b",
    re.I,
)
BOOKING_TOOLS = {
    "calendly.com": "Calendly",
    "acuityscheduling.com": "Acuity Scheduling",
    "cal.com/": "Cal.com",
    "youcanbook.me": "YouCanBookMe",
    "meetings.hubspot.com": "HubSpot Meetings",
    "setmore.com": "Setmore",
    "simplybook.me": "SimplyBook.me",
    "zcal.co": "zcal",
}
CHAT_WIDGETS = {
    "widget.intercom.io": "Intercom",
    "js.intercomcdn.com": "Intercom",
    "js.driftt.com": "Drift",
    "client.crisp.chat": "Crisp",
    "embed.tawk.to": "Tawk.to",
    "cdn.livechatinc.com": "LiveChat",
    "static.zdassets.com": "Zendesk",
    "js.usemessages.com": "HubSpot Chat",
    "code.tidio.co": "Tidio",
    "wchat.freshchat.com": "Freshchat",
}
REVIEW_WIDGETS = {
    "widget.trustpilot.com": "Trustpilot",
    "feefo.com": "Feefo",
    "reviews.io": "REVIEWS.io",
    "elfsight.com": "Elfsight reviews",
}
TESTIMONIAL_TEXT = re.compile(
    r"\b(testimonials?|what our (?:clients|customers) say|client reviews|our clients say)\b", re.I
)
TRUST_TEXT = re.compile(
    r"\b(ISO ?27001|ISO ?9001|Cyber Essentials(?: Plus)?|SRA[- ]regulated|IAA[- ]regulated|"
    r"OISC[- ]regulated|FCA[- ]regulated|accredited by [A-Z][\w ]{2,40}|award[- ]winning|"
    r"Google Partner|Trustpilot)\b"
)
NEWSLETTER = re.compile(r"\b(newsletter|subscribe)\b", re.I)


def _field_kinds(form: Any) -> list[str]:
    kinds: list[str] = []
    for node in form.css("input, textarea, select"):
        kind = (node.attributes.get("type") or node.tag or "").lower()
        name = (node.attributes.get("name") or node.attributes.get("id") or "").lower()
        if kind in ("hidden", "submit", "button", "image", "reset"):
            continue
        if node.tag == "textarea":
            label = "message"
        elif kind == "email" or "email" in name:
            label = "email"
        elif kind == "tel" or "phone" in name or "tel" in name:
            label = "phone"
        elif kind in ("checkbox", "radio"):
            label = kind
        elif "name" in name:
            label = "name"
        else:
            label = kind or "text"
        kinds.append(label)
    return kinds


def _is_search(form: Any) -> bool:
    action = (form.attributes.get("action") or "").lower()
    return (
        form.attributes.get("role") == "search"
        or "search" in action
        or form.css_first('input[type="search"]') is not None
    )


def extract(pages: list[Page], ctx: SiteContext) -> list[Observation]:
    home = next((p for p in pages if p.category == "home"), pages[0])
    checked = [p.url for p in pages]
    out: list[Observation] = []

    def obs(key: str, value: object, page: Page, text: str, **kw: object) -> None:
        out.append(Observation(Area.CONVERSION, f"conversion.{key}", value, page.url, text, **kw))  # type: ignore[arg-type]

    contact_form = newsletter_form = None
    for page in pages:
        for form in page.tree.css("form"):
            if _is_search(form):
                continue
            kinds = _field_kinds(form)
            if not kinds:
                continue
            form_text = " ".join((form.text() or "").split())
            is_newsletter = set(kinds) <= {"email", "checkbox"} and bool(
                NEWSLETTER.search(form_text)
            )
            if is_newsletter and newsletter_form is None:
                newsletter_form = (page, form)
            elif (
                not is_newsletter
                and contact_form is None
                and ({"email", "phone", "message"} & set(kinds))
            ):
                contact_form = (page, form, kinds)
    if contact_form:
        page, form, kinds = contact_form
        obs("contact_form", True, page, outer(form))
        obs("contact_form_fields", kinds, page, outer(form))
    else:
        obs(
            "contact_form",
            False,
            home,
            f"No enquiry form on {len(checked)} crawled pages",
            confidence=0.6,
            seen_on=checked,
        )
    if newsletter_form:
        obs("newsletter_signup", True, newsletter_form[0], outer(newsletter_form[1]))

    emails: list[str] = []
    phones: list[str] = []
    whatsapp: str | None = None
    first: dict[str, Page] = {}
    for page in pages:
        for url, _, _ in links(page):
            low = url.lower()
            if low.startswith("mailto:"):
                address = url[7:].split("?")[0].strip().lower()
                if address and address not in emails:
                    emails.append(address)
                    first.setdefault("email", page)
            elif low.startswith("tel:"):
                number = url[4:].strip()
                if number and number not in phones:
                    phones.append(number)
                    first.setdefault("phone", page)
            elif ("wa.me/" in low or "api.whatsapp.com" in low) and whatsapp is None:
                whatsapp = url
                first["whatsapp"] = page
    if emails:
        obs("email_addresses", emails, first["email"], f"mailto links: {', '.join(emails[:5])}")
    if phones:
        obs("phone_numbers", phones, first["phone"], f"tel links: {', '.join(phones[:5])}")
    if whatsapp:
        obs("whatsapp", True, first["whatsapp"], f"WhatsApp link: {whatsapp}")

    for key, catalogue, absent in (
        ("booking_tool", BOOKING_TOOLS, "No online booking tool"),
        ("live_chat", CHAT_WIDGETS, "No live chat widget"),
        ("reviews_widget", REVIEW_WIDGETS, None),
    ):
        found = _find_vendor(pages, catalogue)
        if found:
            name, page, where = found
            obs(key, name, page, where)
        elif absent:
            obs(
                key,
                None,
                home,
                f"{absent} found on {len(checked)} crawled pages",
                confidence=0.6,
                seen_on=checked,
            )

    ctas: list[str] = []
    for node in home.tree.css("a, button"):
        text = " ".join((node.text() or "").split())
        if 2 <= len(text) <= 40 and CTA.search(text) and text not in ctas:
            ctas.append(text)
    if ctas:
        obs("home_ctas", ctas[:10], home, f"Calls to action on the homepage: {', '.join(ctas[:5])}")
        obs(
            "primary_cta",
            ctas[0],
            home,
            f"First call to action on the homepage: {ctas[0]}",
            confidence=0.7,
        )
    else:
        obs(
            "home_ctas",
            [],
            home,
            "No clear call to action (book, quote, contact, start) on the homepage",
            confidence=0.7,
        )

    testimonial = next(((p, m) for p in pages if (m := TESTIMONIAL_TEXT.search(p.text))), None)
    if testimonial:
        page, match = testimonial
        obs("testimonials", True, page, excerpt(page.text, match.group(0)), confidence=0.8)

    badges: list[str] = []
    badge_page: Page | None = None
    for page in pages:
        for match in TRUST_TEXT.finditer(page.text):
            if match.group(0) not in badges:
                badges.append(match.group(0))
                badge_page = badge_page or page
    if badges and badge_page is not None:
        obs(
            "trust_signals", badges, badge_page, excerpt(badge_page.text, badges[0]), confidence=0.8
        )

    pricing = next((p for p in pages if p.category == "pricing"), None)
    obs(
        "pricing_page",
        pricing is not None,
        pricing or home,
        f"Pricing page: {pricing.url}" if pricing else "No pricing page among crawled pages",
        confidence=0.9 if pricing else 0.6,
    )
    work = next((p for p in pages if p.category == "work"), None)
    if work:
        obs(
            "case_studies_page", True, work, f"Case studies / work page: {work.url}", confidence=0.8
        )
    return out


def _find_vendor(pages: list[Page], catalogue: dict[str, str]) -> tuple[str, Page, str] | None:
    for page in pages:
        candidates = [*script_sources(page), *(url for url, _, _ in links(page))]
        candidates += [n.attributes.get("src") or "" for n in page.tree.css("iframe[src]")]
        for item in candidates:
            for marker, name in catalogue.items():
                if marker in item.lower():
                    return name, page, f"{name}: {item[:200]}"
        html = page.html.lower()
        for marker, name in catalogue.items():
            if marker in html:
                return name, page, f"{name} referenced in page source ({marker})"
    return None
