"""Who may see which accounts: `accounts.read` sees all; `accounts.read_own` sees accounts
owned by the user or not yet owned by anyone."""

import uuid

from sqlalchemy import ColumnElement, or_

from app.accounts.models import Account
from app.auth.models import User

READ_ALL = "accounts.read"
READ_OWN = "accounts.read_own"


def can_see(user: User, owner_id: uuid.UUID | None) -> bool:
    keys = user.permission_keys
    return READ_ALL in keys or (READ_OWN in keys and owner_id in (None, user.id))


def visible(user: User) -> ColumnElement[bool] | None:
    """A WHERE clause limiting accounts to the user's view, or None when they see all."""
    if READ_ALL in user.permission_keys:
        return None
    if READ_OWN in user.permission_keys:
        return or_(Account.owner_id.is_(None), Account.owner_id == user.id)
    return Account.id.is_(None)  # sees nothing
