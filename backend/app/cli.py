"""Server-side admin commands.

    python -m app.cli create-admin --email you@verkies.co --name "Your Name"

The password is prompted for (twice), or read from VROS_ADMIN_PASSWORD for automation.
In Docker:  docker compose exec api python -m app.cli create-admin --email ... --name ...
"""

import argparse
import asyncio
import getpass
import os
import sys

from app.auth import service
from app.core.errors import AppError
from app.db import get_sessionmaker


def _read_password() -> str:
    from_env = os.environ.get("VROS_ADMIN_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Password (12+ characters): ")
    if getpass.getpass("Repeat password: ") != first:
        raise SystemExit("Passwords do not match.")
    return first


async def _create_admin(email: str, name: str, password: str) -> None:
    async with get_sessionmaker()() as db:
        user = await service.create_admin(db, email=email, name=name, password=password)
        await db.commit()
        print(f"Admin created: {user.email}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-admin", help="create an admin account")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-admin":
        try:
            asyncio.run(_create_admin(args.email, args.name, _read_password()))
        except AppError as exc:
            print(f"Error: {exc.message}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
