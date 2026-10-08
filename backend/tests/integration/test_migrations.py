import pytest
from sqlalchemy import Engine, text

from alembic import command
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration


def test_downgrade_to_base_and_back_is_clean(engine: Engine, database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    with engine.connect() as conn:
        left = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
        ).scalar_one()
    assert left == 1  # only alembic_version remains
    command.upgrade(config, "head")


def test_models_and_migrations_do_not_drift(database_url: str) -> None:
    command.check(alembic_config(database_url))  # raises if autogenerate finds differences


def test_reference_data_is_seeded(engine: Engine) -> None:
    with engine.connect() as conn:
        counts = {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608
            for table in ("roles", "permissions", "opportunity_categories", "services")
        }
        unconfirmed = conn.execute(
            text("SELECT count(*) FROM services WHERE NOT confirmed")
        ).scalar_one()
        complete = conn.execute(
            text("SELECT count(*) FROM reference_projects WHERE profile_complete")
        ).scalar_one()
        wesbridge = conn.execute(
            text(
                "SELECT array_agg(s.key ORDER BY s.key) FROM reference_projects rp "
                "JOIN reference_project_services rps ON rps.reference_project_id = rp.id "
                "JOIN services s ON s.id = rps.service_id WHERE rp.name = 'Wesbridge Associates'"
            )
        ).scalar_one()
    assert counts == {"roles": 7, "permissions": 7, "opportunity_categories": 25, "services": 15}
    assert unconfirmed == 0
    assert complete == 0  # unknown fields stay unknown until Verkies fills them in
    assert wesbridge == ["crm_portal", "public_tools", "seo_content", "web_dev"]


def test_admin_holds_every_permission(engine: Engine) -> None:
    with engine.connect() as conn:
        missing = conn.execute(
            text(
                "SELECT p.key FROM permissions p WHERE NOT EXISTS ("
                " SELECT 1 FROM role_permissions rp JOIN roles r ON r.id = rp.role_id"
                " WHERE r.key = 'admin' AND rp.permission_id = p.id)"
            )
        ).all()
    assert missing == []


def test_seeded_catalogue_matches_code_defaults(engine: Engine) -> None:
    from app.catalogue.defaults import SERVICES

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT key, solves FROM services ORDER BY key")).all()
    assert {k: s for k, s in rows} == {k: solves for k, _, solves, _ in SERVICES}


def test_default_configs_are_seeded_valid_and_active(engine: Engine) -> None:
    from app.qualification.config import IcpConfigModel
    from app.scoring.config import ScoringConfigModel

    with engine.connect() as conn:
        icp = conn.execute(text("SELECT config FROM icp_configs WHERE is_active")).scalar_one()
        scoring = conn.execute(
            text("SELECT config FROM scoring_configs WHERE is_active")
        ).scalar_one()
    assert IcpConfigModel.model_validate(icp) == IcpConfigModel()
    assert ScoringConfigModel.model_validate(scoring) == ScoringConfigModel()
