"""Saved views (master context §13, slice 3.3): a named link to a VROS page with its filters."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, CreatedMixin, IdMixin


class SavedView(IdMixin, CreatedMixin, Base):
    """A page and its query string, e.g. `/leads` with `q=my hot leads`.

    `user_id` NULL means the view is shared with the whole team. Only the path and query are
    stored, so a view always shows today's data through the page's own permissions.
    """

    __tablename__ = "saved_views"
    __table_args__ = (CheckConstraint("path LIKE '/%'", name="path_is_local"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(1000), default="")
    position: Mapped[int] = mapped_column(SmallInteger, default=0)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
