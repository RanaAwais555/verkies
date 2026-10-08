"""Fixture websites for extractor tests: realistic HTML, no network."""

from app.intelligence.types import Page, SiteContext

SAAS_FILLER = (
    "Shiplane is a cloud platform for dispatch, fleet tracking and proof of delivery. Plans are per user per month with a free trial and integrations with your accounting software. "
    * 6
)
FILLER = "We help families and skilled workers with UK visas, settlement and citizenship. " * 8

IMMIGRATION_HOME = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><title>Harbour Immigration | UK Visa Advisers in London</title>
<meta name="description" content="IAA-regulated immigration advisers in the City of London helping with spouse, skilled worker and settlement visas.">
<meta name="generator" content="WordPress 5.2.4">
<link rel="stylesheet" href="/wp-content/themes/harbour/style.css">
<script src="/wp-includes/js/jquery/jquery.min.js"></script>
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"LegalService",
 "name":"Harbour Immigration Ltd","address":{{"@type":"PostalAddress","streetAddress":"1 Cheapside",
 "addressLocality":"London","postalCode":"EC2V 6AA","addressCountry":"GB"}}}}</script>
</head><body>
<header><a href="/about-us/">About us</a><a href="/our-team/">Our team</a><a href="/contact/">Contact us</a></header>
<h1>UK immigration advice you can trust</h1>
<p>{FILLER}</p>
<p>What our clients say: "Harbour made the process painless."</p>
<p>We are IAA-regulated and award-winning.</p>
<img src="/wp-content/uploads/hero.jpg"><img src="/wp-content/uploads/team.jpg" alt="Our team">
<footer><a href="tel:+44 20 7946 0001">020 7946 0001</a>
<a href="mailto:info@harbourimmigration.co.uk">info@harbourimmigration.co.uk</a>
<a href="https://www.linkedin.com/company/harbour-immigration">LinkedIn</a>
<a href="https://www.facebook.com/sharer/sharer.php?u=x">Share</a>
<a href="/old-fees/">Fees</a>
<p>© 2017 Harbour Immigration Ltd. Established in 2009.</p></footer>
</body></html>"""

IMMIGRATION_CONTACT = f"""<html><head><title>Contact</title></head><body><h1>Contact</h1>
<form action="/wp-admin/admin-post.php" method="post"><input type="text" name="your-name">
<input type="email" name="your-email"><input type="tel" name="your-phone"><textarea name="message"></textarea>
<input type="hidden" name="_wpnonce" value="x"><button type="submit">Send</button></form>
<form role="search" action="/"><input type="search" name="s"></form><p>{FILLER}</p></body></html>"""

IMMIGRATION_TEAM = f"""<html><head><title>Our team</title></head><body><h1>Meet the team</h1>
<div class="card"><h3>Amelia Hart</h3><p>Founder and Senior Immigration Adviser</p></div>
<div class="card"><h3>Daniel Okafor</h3><p>Head of Operations</p></div>
<div class="card"><h3>Our Values</h3><p>Integrity first</p></div>
<p>{FILLER}</p></body></html>"""

IMMIGRATION_ABOUT = f"<html><head><title>About</title></head><body><h1>About</h1><h1>Story</h1><p>{FILLER}</p></body></html>"

IMMIGRATION = (
    [
        Page(
            "https://harbourimmigration.co.uk/",
            IMMIGRATION_HOME,
            "home",
            {"server": "Apache", "x-powered-by": "PHP/7.2.1"},
            len(IMMIGRATION_HOME),
        ),
        Page("https://harbourimmigration.co.uk/contact/", IMMIGRATION_CONTACT, "contact", {}, 900),
        Page("https://harbourimmigration.co.uk/our-team/", IMMIGRATION_TEAM, "team", {}, 900),
        Page("https://harbourimmigration.co.uk/about-us/", IMMIGRATION_ABOUT, "about", {}, 800),
    ],
    SiteContext(
        home_url="https://harbourimmigration.co.uk/",
        robots="missing",
        sitemaps=(),
        statuses={
            "https://harbourimmigration.co.uk/": 200,
            "https://harbourimmigration.co.uk/contact/": 200,
            "https://harbourimmigration.co.uk/our-team/": 200,
            "https://harbourimmigration.co.uk/about-us/": 200,
            "https://harbourimmigration.co.uk/old-fees/": 404,
        },
    ),
)

SAAS_HOME = f"""<!doctype html><html><head><title>Shiplane — Logistics software for growing fleets</title>
<meta name="description" content="Shiplane is the dispatch and tracking platform for regional logistics companies.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="Shiplane"><meta property="og:site_name" content="Shiplane">
<link rel="canonical" href="https://shiplane.io/">
<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>
<script src="https://widget.intercom.io/widget/abc123"></script>
<script type="application/ld+json">{{"@graph":[{{"@type":"Organization","name":"Shiplane Inc"}},
 {{"@type":"WebSite","name":"Shiplane"}}]}}</script>
</head><body><div id="__next">
<nav><a href="/login">Log in</a><a href="/signup">Start free trial</a><a href="/pricing">Pricing</a>
<a href="/careers">Careers</a></nav>
<h1>Dispatch without the spreadsheets</h1>
<a href="https://calendly.com/shiplane/demo">Book a demo</a>
<p>{SAAS_FILLER}</p>
<a href="https://apps.apple.com/app/shiplane/id123">Download on the App Store</a>
<a href="https://docs.shiplane.io/api">API docs</a>
<a href="https://x.com/shiplane">X</a><a href="https://www.linkedin.com/company/shiplane/">LinkedIn</a>
<footer>© 2015–2026 Shiplane Inc</footer>
</div><script id="__NEXT_DATA__" type="application/json">{{}}</script>
<script src="/_next/static/chunks/main.js"></script></body></html>"""

SAAS_PRICING = f"""<html><head><title>Pricing</title></head><body><h1>Pricing</h1>
<p>Starter £49 per month. Growth £149 per month, billed annually.</p>
<script src="https://js.stripe.com/v3/"></script><p>{SAAS_FILLER}</p></body></html>"""

SAAS_CAREERS = f"""<html><head><title>Careers</title></head><body><h1>Join us</h1>
<ul><li><a href="https://boards.greenhouse.io/shiplane/jobs/1">Senior Backend Engineer</a></li>
<li><a href="https://boards.greenhouse.io/shiplane/jobs/2">Product Manager</a></li>
<li>Account Executive</li></ul><p>{SAAS_FILLER}</p></body></html>"""

SAAS = (
    [
        Page(
            "https://shiplane.io/",
            SAAS_HOME,
            "home",
            {
                "strict-transport-security": "max-age=63072000",
                "content-security-policy": "default-src 'self'",
                "x-vercel-id": "lhr1::abc",
                "server": "Vercel",
            },
            len(SAAS_HOME),
        ),
        Page("https://shiplane.io/pricing", SAAS_PRICING, "pricing", {}, 700),
        Page("https://shiplane.io/careers", SAAS_CAREERS, "careers", {}, 700),
    ],
    SiteContext(
        home_url="https://shiplane.io/",
        robots="parsed",
        sitemaps=("https://shiplane.io/sitemap.xml",),
    ),
)

HOLDING_HTML = (
    "<html><head><title>Coming soon</title></head><body><p>Coming soon.</p></body></html>"
)
HOLDING = (
    [Page("http://quiet.example/", HOLDING_HTML, "home", {}, len(HOLDING_HTML))],
    SiteContext(home_url="http://quiet.example/", robots="missing"),
)


def _single(url: str, html: str, **ctx: object) -> tuple[list[Page], SiteContext]:
    return [Page(url, html, "home", {}, len(html))], SiteContext(
        home_url=url, robots="missing", **ctx
    )  # type: ignore[arg-type]


PARKED = _single(
    "https://bestwidgets.example/",
    "<html><head><title>bestwidgets.example</title></head><body><h1>bestwidgets.example</h1>"
    "<p>This domain is for sale! Buy this domain today. Contact our broker.</p></body></html>",
)

AGENCY_BODY = (
    "Pixelforge is a digital agency in Manchester. We build websites for ambitious brands and "
    "offer white-label services to other studios. Our clients include retailers and charities. "
    "Web design, SEO and paid social for growing companies. "
) * 5
AGENCY = _single(
    "https://pixelforge.example/",
    f"""<html><head><title>Pixelforge | Digital Agency</title>
<meta name="description" content="Pixelforge is a Manchester digital agency for web design, SEO and paid social.">
<script type="application/ld+json">{{"@type":"Organization","name":"Pixelforge",
 "address":{{"@type":"PostalAddress","addressLocality":"Manchester","addressCountry":"GB"}}}}</script>
</head><body><h1>We make brands grow online</h1><p>{AGENCY_BODY}</p>
<a href="/contact">Get a quote</a><a href="mailto:hello@pixelforge.example">Email</a>
<h3>Jo Fielding</h3><p>Founder and Creative Director</p>
<footer>© 2026 Pixelforge</footer></body></html>""",
)

FREELANCER = _single(
    "https://samdoes.dev/",
    """<html><head><title>Sam Rivers — Freelance Web Developer</title></head><body>
<h1>Hi, I'm Sam</h1><p>I'm a freelance web developer building WordPress sites and React apps.
I'm available for freelance work. Hire me for your next project, or view my work below.
Download my CV.</p><a href="mailto:sam@samdoes.dev">Hire me</a><footer>© 2026 Sam Rivers</footer>
</body></html>""",
)

CLOSED = _single(
    "https://oldmill-bakery.example/",
    """<html><head><title>Old Mill Bakery</title></head><body><h1>Old Mill Bakery</h1>
<p>After 30 years we have now closed. Thank you to all our customers. The bakery ceased trading in
March and the shop is permanently closed.</p><footer>© 2024 Old Mill Bakery</footer></body></html>""",
)
