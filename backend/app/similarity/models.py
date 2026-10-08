"""Similarity between a researched prospect and Verkies' reference projects (§11)."""

import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin, Score, score, score_checks


class SimilarityResult(IdMixin, CreatedMixin, Base):
    __tablename__ = "similarity_results"
    __table_args__ = (
        UniqueConstraint("research_run_id", "reference_project_id"),
        *score_checks("similarity_score"),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE")
    )
    reference_project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reference_projects.id"))
    similarity_score: Score = score()
    similar_because: Mapped[str] = mapped_column(Text, default="")
