"""The seeded service catalogue (migration 0003), for code and tests that run without a
database. tests/integration/test_migrations.py checks this matches what the migration seeds."""

SITE = "https://www.verkies.co/"
SERVICES: list[tuple[str, str, list[str], str | None]] = [
    (
        "custom_software",
        "Custom Software Development",
        [
            "product_rebuild",
            "technical_rescue",
            "application_modernization",
            "internal_tools",
            "workflow_automation",
            "integrations",
            "digital_transformation",
        ],
        SITE,
    ),
    ("saas_dev", "SaaS Development", ["saas_development", "marketplace"], SITE),
    ("mvp_startups", "MVPs for startups", ["mvp_development"], SITE),
    ("web_dev", "Web Development", ["website_rebuild"], SITE),
    ("mobile_dev", "Mobile Application Development", ["mobile_application"], SITE),
    (
        "crm_portal",
        "CRM, practice systems and client portals",
        [
            "crm",
            "client_portal",
            "customer_onboarding",
            "document_workflow",
            "payment_workflow",
            "workflow_automation",
        ],
        SITE,
    ),
    (
        "public_tools",
        "Public tools (instant quote, eligibility, booking)",
        ["booking_system", "conversion_optimization", "customer_onboarding"],
        SITE,
    ),
    (
        "database_dev",
        "Database Development",
        ["integrations", "document_workflow", "analytics"],
        None,
    ),
    (
        "ux_design",
        "User Experience Design (UED)",
        ["conversion_optimization", "product_rebuild"],
        SITE,
    ),
    ("project_management", "Project Management", ["ongoing_product_support"], None),
    (
        "seo_content",
        "SEO and content engine",
        ["seo", "content_strategy"],
        "https://www.verkies.co/case/wesbridge",
    ),
    ("brand", "Brand and identity", ["growth_marketing"], SITE),
    (
        "growth_marketing",
        "Growth Marketing",
        ["growth_marketing", "paid_acquisition", "content_strategy", "analytics"],
        SITE,
    ),
    ("demand_generation", "Demand Generation", ["paid_acquisition", "growth_marketing"], None),
    ("business_consulting", "Business Consulting", ["digital_transformation"], None),
]


def solved_by(
    services: list[tuple[str, str, list[str], str | None]] = SERVICES,
) -> dict[str, list[str]]:
    """Opportunity category -> confirmed service keys that answer it, in catalogue order."""
    mapping: dict[str, list[str]] = {}
    for key, _, solves, _ in services:
        for category in solves:
            mapping.setdefault(category, []).append(key)
    return mapping
