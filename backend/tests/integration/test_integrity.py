"""Database-level integrity rules (DATA_MODEL.md §6)."""

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.integration


def _account(conn, domain: str | None = "acme.test", deleted: bool = False) -> uuid.UUID:  # type: ignore[no-untyped-def]
    account_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO accounts (id, name, primary_domain, account_type, deleted_at)"
            " VALUES (:id, 'Acme', :d, 'prospect', CASE WHEN :del THEN now() END)"
        ),
        {"id": account_id, "d": domain, "del": deleted},
    )
    return account_id


def _evidence(conn, account_id: uuid.UUID | None = None) -> uuid.UUID:  # type: ignore[no-untyped-def]
    evidence_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO evidence (id, account_id, source_url, source_domain, collected_at,"
            " evidence_type, evidence_text, content_hash, confidence)"
            " VALUES (:id, :a, 'https://acme.test/', 'acme.test', now(), 'page_content',"
            " 'Contact us via the form', 'h', 0.9)"
        ),
        {"id": evidence_id, "a": account_id},
    )
    return evidence_id


def _claim(conn, claim_class: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    claim_id = uuid.uuid4()
    conn.execute(
        text(
            "INSERT INTO claims (id, claim_class, subject, statement, confidence)"
            " VALUES (:id, :c, 'conversion.primary_cta', 'Only a generic contact form', 0.8)"
        ),
        {"id": claim_id, "c": claim_class},
    )
    return claim_id


def test_one_live_account_per_domain(engine: Engine) -> None:
    with engine.begin() as conn:
        _account(conn)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _account(conn)


def test_soft_deleted_account_frees_its_domain(engine: Engine) -> None:
    with engine.begin() as conn:
        _account(conn, deleted=True)
        _account(conn)  # no error


@pytest.mark.parametrize("claim_class", ["fact", "inference"])
def test_fact_and_inference_claims_need_evidence(engine: Engine, claim_class: str) -> None:
    with pytest.raises(IntegrityError, match="cites no evidence"), engine.begin() as conn:
        _claim(conn, claim_class)


def test_claim_with_evidence_commits_in_any_order(engine: Engine) -> None:
    with engine.begin() as conn:
        claim_id = _claim(conn, "fact")  # evidence link inserted afterwards, same transaction
        evidence_id = _evidence(conn)
        conn.execute(
            text("INSERT INTO claim_evidence (claim_id, evidence_id) VALUES (:c, :e)"),
            {"c": claim_id, "e": evidence_id},
        )


def test_recommendation_must_rest_on_claims(engine: Engine) -> None:
    with pytest.raises(IntegrityError, match="rests on no claims"), engine.begin() as conn:
        _claim(conn, "recommendation")
    with engine.begin() as conn:
        fact = _claim(conn, "fact")
        conn.execute(
            text("INSERT INTO claim_evidence VALUES (:c, :e)"), {"c": fact, "e": _evidence(conn)}
        )
        rec = _claim(conn, "recommendation")
        conn.execute(text("INSERT INTO claim_support VALUES (:r, :f)"), {"r": rec, "f": fact})


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE evidence SET evidence_text = 'edited'",
        "DELETE FROM evidence",
    ],
)
def test_evidence_is_append_only(engine: Engine, statement: str) -> None:
    with engine.begin() as conn:
        _evidence(conn)
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(statement))


def test_evidence_can_be_attached_to_an_account_once(engine: Engine) -> None:
    with engine.begin() as conn:
        evidence_id = _evidence(conn)
        first = _account(conn, "one.test")
        second = _account(conn, "two.test")
        conn.execute(
            text("UPDATE evidence SET account_id = :a WHERE id = :e"),
            {"a": first, "e": evidence_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(
            text("UPDATE evidence SET account_id = :a WHERE id = :e"),
            {"a": second, "e": evidence_id},
        )


def test_attaching_cannot_smuggle_other_changes(engine: Engine) -> None:
    with engine.begin() as conn:
        evidence_id = _evidence(conn)
        account_id = _account(conn)
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(
            text("UPDATE evidence SET account_id = :a, evidence_text = 'x' WHERE id = :e"),
            {"a": account_id, "e": evidence_id},
        )


@pytest.mark.parametrize("table", ["audit_log", "timeline_events"])
def test_audit_and_timeline_are_append_only(engine: Engine, table: str) -> None:
    with engine.begin() as conn:
        if table == "audit_log":
            conn.execute(
                text(
                    "INSERT INTO audit_log (id, object_table, action, source)"
                    " VALUES (gen_random_uuid(), 'users', 'x', 'system')"
                )
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO timeline_events (id, account_id, event_type, summary)"
                    " VALUES (gen_random_uuid(), :a, 'discovered', 'x')"
                ),
                {"a": _account(conn)},
            )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608


@pytest.mark.parametrize("value", [-1, 100.01])
def test_scores_stay_within_0_to_100(engine: Engine, value: float) -> None:
    with pytest.raises(IntegrityError, match="icp_score_range"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, account_type, icp_score)"
                " VALUES (gen_random_uuid(), 'X', 'prospect', :v)"
            ),
            {"v": value},
        )


def test_unknown_score_is_null_not_zero(engine: Engine) -> None:
    with engine.begin() as conn:
        account_id = _account(conn)
        assert (
            conn.execute(
                text("SELECT icp_score FROM accounts WHERE id = :a"), {"a": account_id}
            ).scalar_one()
            is None
        )


def test_enums_reject_unknown_values(engine: Engine) -> None:
    with pytest.raises(IntegrityError, match="accounttype"), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO accounts (id, name, account_type)"
                " VALUES (gen_random_uuid(), 'X', 'lead_maybe')"
            )
        )


def test_only_one_active_scoring_config(engine: Engine) -> None:
    insert = text(
        "INSERT INTO scoring_configs (id, version, is_active, config)"
        " VALUES (gen_random_uuid(), :v, :a, '{}')"
    )
    with engine.begin() as conn:  # version 1 is seeded and active
        conn.execute(insert, {"v": 2, "a": False})
    with pytest.raises(IntegrityError, match="single_active"), engine.begin() as conn:
        conn.execute(insert, {"v": 3, "a": True})


def test_service_matches_one_per_slot(engine: Engine) -> None:
    with engine.begin() as conn:
        user_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO users (id, email, name, password_hash, is_active, failed_login_count)"
                " VALUES (:id, 'r@x.test', 'R', 'x', true, 0)"
            ),
            {"id": user_id},
        )
        run_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO research_runs (id, input_url, normalised_domain, requested_by_id,"
                " status, review_status, retry_count, crawl_budget, possible_duplicate_of)"
                " VALUES (:id, 'https://acme.test', 'acme.test', :u, 'queued', 'pending', 0,"
                " '{}', '[]')"
            ),
            {"id": run_id, "u": user_id},
        )
        insert = text(
            "INSERT INTO service_matches (id, research_run_id, slot, service_id, rationale,"
            " confidence) SELECT gen_random_uuid(), :r, :slot, id, 'x', 0.5 FROM services"
            " WHERE key = 'crm_portal'"
        )
        conn.execute(insert, {"r": run_id, "slot": "primary"})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert, {"r": run_id, "slot": "primary"})
    with pytest.raises(IntegrityError, match="serviceslot"), engine.begin() as conn:
        conn.execute(insert, {"r": run_id, "slot": "fourth"})
