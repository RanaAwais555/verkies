"""integrity rules: append-only tables and evidence-backed claims

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

DATA_MODEL.md §6. These rules hold whatever code writes to the database.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> column that may be filled in once (NULL -> value), e.g. when a prospect is approved
# and its research evidence is attached to the new Account. Every other change is refused.
APPEND_ONLY: dict[str, str | None] = {
    "evidence": "account_id",
    "claims": "account_id",
    "claim_evidence": None,
    "claim_support": None,
    "score_snapshots": "account_id",
    "audit_log": None,
    "timeline_events": None,
}


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION vros_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            attach text := TG_ARGV[0];
        BEGIN
            IF TG_OP = 'UPDATE' AND attach IS NOT NULL
               AND (to_jsonb(OLD) ->> attach) IS NULL
               AND (to_jsonb(NEW) ->> attach) IS NOT NULL
               AND (to_jsonb(NEW) - attach) = (to_jsonb(OLD) - attach) THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for table, attach in APPEND_ONLY.items():
        args = f"'{attach}'" if attach else ""
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION vros_append_only({args})"
        )

    # Checked at commit, so a claim and its evidence links can be inserted in any order.
    op.execute(
        """
        CREATE FUNCTION vros_claim_is_supported() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.claim_class IN ('fact', 'inference') AND NOT EXISTS (
                SELECT 1 FROM claim_evidence WHERE claim_id = NEW.id
            ) THEN
                RAISE EXCEPTION '% claim % cites no evidence', NEW.claim_class, NEW.id
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NEW.claim_class = 'recommendation' AND NOT EXISTS (
                SELECT 1 FROM claim_support WHERE claim_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'recommendation % rests on no claims', NEW.id
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_claims_supported AFTER INSERT ON claims "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION vros_claim_is_supported()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_claims_supported ON claims")
    op.execute("DROP FUNCTION vros_claim_is_supported()")
    for table in APPEND_ONLY:
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION vros_append_only()")
