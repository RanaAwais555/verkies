"""Resets the database for an end-to-end run: empty schema, all migrations, one admin.

    VROS_ADMIN_PASSWORD=... python -m tests.fixtures.e2e_reset admin@example.test "Ada Admin"

Destroys every row in the configured database; refuses to run in production.
"""

import asyncio
import os
import sys

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.auth import service
from app.config import get_settings
from app.db import get_sessionmaker

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _admin(email: str, name: str, password: str) -> None:
    async with get_sessionmaker()() as db:
        await service.create_admin(db, email=email, name=name, password=password)
        await db.commit()


def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("Refusing to reset a production database.")
    email, name = sys.argv[1], sys.argv[2]
    password = os.environ["VROS_ADMIN_PASSWORD"]
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.attributes["database_url"] = settings.database_url
    command.upgrade(config, "head")
    asyncio.run(_admin(email, name, password))
    print(f"database reset; admin {email}", flush=True)


if __name__ == "__main__":
    main()
