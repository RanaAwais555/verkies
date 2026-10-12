"""Slice 5.4: won clients become similarity references."""

import asyncio
import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.research.models import ResearchRun
from app.scoring.stage import references
from app.similarity.engine import ReferenceProfile, compare
from tests.integration.conftest import ApiClient, make_user
from tests.integration.test_clients import won_deal
from tests.integration.test_win_loss import close

pytestmark = pytest.mark.integration


@pytest.fixture
def admin(engine: Engine, api: ApiClient) -> uuid.UUID:
    user_id = make_user(engine, "ada@verkies.test", ["admin"], name="Ada Admin")
    api.login("ada@verkies.test")
    return user_id


def profiles(run: ResearchRun | None = None) -> list[ReferenceProfile]:
    async def load() -> list[ReferenceProfile]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with async_sessionmaker(engine, class_=AsyncSession)() as db:
                return await references(db, run)
        finally:
            await engine.dispose()

    return asyncio.run(load())


def test_won_clients_become_references(engine: Engine, api: ApiClient, admin: uuid.UUID) -> None:
    deal = won_deal(engine, api, admin, "Acme Legal")  # legal, Web Development, won
    close(engine, api, admin, "Lost Firm", won=False, industry="legal")
    nameless = close(engine, api, admin, "Mystery Co", won=True, industry="legal")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE accounts SET industry = 'legal' WHERE id = :a"), {"a": deal["account_id"]}
        )
        # Recorded before its industry was known: an incomplete profile, never compared.
        conn.execute(
            text("UPDATE deal_outcomes SET industry = NULL WHERE deal_id = :d"),
            {"d": nameless["deal_id"]},
        )
        conn.execute(
            text("UPDATE deal_outcomes SET industry = 'legal' WHERE deal_id = :d"),
            {"d": deal["id"]},
        )

    clients = {p.name: p for p in profiles() if p.kind == "client"}
    assert set(clients) == {"Acme Legal", "Mystery Co"}  # the lost deal is no reference
    acme = clients["Acme Legal"]
    assert acme.profile_complete and acme.industry == "legal"
    assert acme.service_keys == ("web_dev",) and acme.problem == "Found on their site"
    assert acme.ref_id == uuid.UUID(deal["account_id"])
    assert not clients["Mystery Co"].profile_complete
    assert (
        compare(clients["Mystery Co"], industries=["legal"], problems=[], matches=[]).score is None
    )

    result = compare(acme, industries=["legal"], problems=["Clients email documents"], matches=[])
    assert result.kind == "client" and result.score == 30.0
    assert result.because == "Similar because same industry (legal)"

    # Researching the client's own site never compares it with itself.
    own = ResearchRun(normalised_domain="acme.test", account_id=None)
    assert all(p.name != "Acme Legal" for p in profiles(own))
    assert any(p.kind == "project" for p in profiles(own))  # reference projects stay


def test_a_result_points_at_exactly_one_reference(engine: Engine, admin: uuid.UUID) -> None:
    with engine.begin() as conn:
        run_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of)"
                " VALUES (:id, 'https://x.test/', 'x.test', :u, 'completed', 'pending', 0, '{}',"
                " '[]')"
            ),
            {"id": run_id, "u": admin},
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO similarity_results (id, research_run_id, similar_because)"
                " VALUES (gen_random_uuid(), :r, 'neither')"
            ),
            {"r": run_id},
        )
