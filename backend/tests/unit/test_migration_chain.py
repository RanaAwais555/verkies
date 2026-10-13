"""Migrations form one line: every file has its own revision and there is a single head.

Two pull requests can each add the next number and pass on their own; merged together they
break `alembic upgrade head`. This catches it without a database.
"""

import os
import warnings
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[2]


def scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(os.path.join(BACKEND_DIR, "alembic.ini")))


def test_every_migration_has_its_own_revision() -> None:
    files = sorted((BACKEND_DIR / "alembic" / "versions").glob("[0-9]*.py"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # alembic warns on a duplicate and keeps only one
        revisions = list(scripts().walk_revisions())
    assert len(revisions) == len(files), "two migration files share a revision id"


def test_there_is_one_head() -> None:
    assert len(scripts().get_heads()) == 1
