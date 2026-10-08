"""reference data: roles, permissions, opportunity categories, services, reference projects

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

Sources: SECURITY.md §2 (roles), master context §9 (categories), VERKIES_PROFILE.md §3a
(services, confirmed by Verkies 2026-10-08) and §4 (reference projects, public-site facts only;
unknown fields stay NULL and profile_complete is false).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "research.run": "Start research on a company URL",
    "prospects.review": "Approve or reject researched prospects",
    "accounts.read": "View all accounts, leads and tasks",
    "accounts.read_own": "View accounts and leads owned by you or unassigned",
    "config.manage": "Edit ICP, scoring, service catalogue and reference projects",
    "audit.read": "View the audit log",
    "users.manage": "Invite, deactivate and change roles of team members",
}

ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Admin", list(PERMISSIONS)),
    "founder": (
        "Founder / Management",
        ["research.run", "prospects.review", "accounts.read", "audit.read"],
    ),
    "sales_manager": (
        "Sales Manager",
        ["research.run", "prospects.review", "accounts.read", "audit.read"],
    ),
    "salesperson": ("Salesperson", ["research.run", "prospects.review", "accounts.read_own"]),
    "researcher": ("Researcher", ["research.run", "accounts.read"]),
    "project_manager": ("Project Manager", ["accounts.read"]),
    "viewer": ("Viewer", ["accounts.read"]),
}

CATEGORIES = {
    "mvp_development": "MVP development",
    "saas_development": "SaaS development",
    "product_rebuild": "Product rebuild",
    "technical_rescue": "Technical rescue",
    "application_modernization": "Application modernization",
    "website_rebuild": "Website rebuild",
    "mobile_application": "Mobile application",
    "marketplace": "Marketplace",
    "crm": "CRM",
    "client_portal": "Client portal",
    "workflow_automation": "Workflow automation",
    "internal_tools": "Internal tools",
    "digital_transformation": "Digital transformation",
    "booking_system": "Booking system",
    "document_workflow": "Document workflow",
    "customer_onboarding": "Customer onboarding",
    "payment_workflow": "Payment workflow",
    "seo": "SEO",
    "content_strategy": "Content strategy",
    "conversion_optimization": "Conversion optimization",
    "paid_acquisition": "Paid acquisition",
    "growth_marketing": "Growth marketing",
    "analytics": "Analytics",
    "integrations": "Integrations",
    "ongoing_product_support": "Ongoing product support",
}

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

# name, industry, problem, services, status, website. Everything else is Unknown (NULL).
REFERENCE_PROJECTS: list[tuple[str, str, str, list[str], str, str, str]] = [
    (
        "Oerno",
        "Travel / consumer startup",
        "A travel planner that books trips from one chat; Verkies is building it end to end.",
        ["mvp_startups"],
        "In progress, early access open",
        "https://oerno.com",
        SITE,
    ),
    (
        "ShiftRow",
        "UK moving service",
        "Instant quotes for a moving service; needed a brand, website, booking tools and a CRM.",
        ["brand", "web_dev", "public_tools", "crm_portal"],
        "Live and quoting",
        "https://shiftrow.co.uk",
        SITE,
    ),
    (
        "Wesbridge Associates",
        "UK immigration advice (IAA-regulated)",
        "Broken WordPress site nobody could update; enquiries answered by email when someone had time; client details retyped into documents; case progress held in people's heads; letters assembled by hand.",
        ["web_dev", "seo_content", "crm_portal", "public_tools"],
        "Live, tools in use",
        "https://www.wesbridgeassociates.co.uk",
        "https://www.verkies.co/case/wesbridge",
    ),
    (
        "THEOO",
        "Property",
        "Property, experienced differently; a website and the CRM that runs it.",
        ["web_dev", "crm_portal"],
        "Live, waitlist open",
        "https://www.welovetheoo.com",
        SITE,
    ),
    (
        "LumiNexis TBG",
        "UK founder validation / business launch",
        "Helps UK founders validate and launch businesses; the CRM their client work runs on.",
        ["crm_portal"],
        "CRM in production",
        "https://luminexistbg.com",
        SITE,
    ),
    (
        "Ask iDeer",
        "Startup consulting",
        "Startup consulting from idea to investor-ready; their CRM.",
        ["crm_portal"],
        "CRM in production",
        "https://askideer.com",
        SITE,
    ),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, description in PERMISSIONS.items():
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, key, description) VALUES (gen_random_uuid(), :k, :d)"
            ),
            {"k": key, "d": description},
        )
    for key, (name, permissions) in ROLES.items():
        conn.execute(
            sa.text(
                "INSERT INTO roles (id, key, name, description) VALUES (gen_random_uuid(), :k, :n, '')"
            ),
            {"k": key, "n": name},
        )
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM roles r, permissions p WHERE r.key = :k AND p.key = ANY(:perms)"
            ),
            {"k": key, "perms": permissions},
        )
    for key, name in CATEGORIES.items():
        conn.execute(
            sa.text(
                "INSERT INTO opportunity_categories (id, key, name, is_active) VALUES (gen_random_uuid(), :k, :n, true)"
            ),
            {"k": key, "n": name},
        )
    for key, name, solves, source in SERVICES:
        conn.execute(
            sa.text(
                "INSERT INTO services (id, key, name, description, solves, source_url, confirmed, is_active) "
                "VALUES (gen_random_uuid(), :k, :n, '', CAST(:s AS jsonb), :src, true, true)"
            ),
            {"k": key, "n": name, "s": json.dumps(solves), "src": source},
        )
    for name, industry, problem, services, status, website, source in REFERENCE_PROJECTS:
        conn.execute(
            sa.text(
                "INSERT INTO reference_projects (id, name, industry, problem, status, website_url, source_url, profile_complete) "
                "VALUES (gen_random_uuid(), :n, :i, :p, :st, :w, :src, false)"
            ),
            {"n": name, "i": industry, "p": problem, "st": status, "w": website, "src": source},
        )
        conn.execute(
            sa.text(
                "INSERT INTO reference_project_services (reference_project_id, service_id) "
                "SELECT rp.id, s.id FROM reference_projects rp, services s WHERE rp.name = :n AND s.key = ANY(:keys)"
            ),
            {"n": name, "keys": services},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "reference_project_services",
        "reference_projects",
        "services",
        "opportunity_categories",
        "role_permissions",
        "roles",
        "permissions",
    ):
        conn.execute(sa.text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table names
