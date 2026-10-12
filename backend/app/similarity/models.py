"""Similarity between a researched prospect and Verkies' reference projects (§11) or, since slice
5.4, the clients Verkies won."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin, Score, score, score_checks


class SimilarityResult(IdMixin, CreatedMixin, Base):
    __tablename__ = "similarity_results"
    __table_args__ = (
        UniqueConstraint("research_run_id", "reference_project_id"),
        UniqueConstraint("research_run_id", "client_account_id"),
        CheckConstraint(
            "(reference_project_id IS NULL) <> (client_account_id IS NULL)", name="one_reference"
        ),
        *score_checks("similarity_score"),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    reference_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("reference_projects.id")
    )
    client_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    similarity_score: Score = score()
    similar_because: Mapped[str] = mapped_column(Text, default="")
