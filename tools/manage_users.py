#!/usr/bin/env python3
"""Manage local Notifinho accounts from the trusted host or container shell."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from storage.database import Database  # noqa: E402
from storage.users import UserStore  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--state-dir",
        default=os.environ.get("NOTIFINHO_STATE_DIR", "/notifinho/state"),
        help="owner-only state directory (default: NOTIFINHO_STATE_DIR or /notifinho/state)",
    )
    commands = value.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="create or migrate the state database")

    create_admin = commands.add_parser(
        "create-admin",
        help="create the first account as an administrator",
    )
    create_admin.add_argument("--username", required=True)
    create_admin.add_argument("--password-env")

    create_user = commands.add_parser("create-user", help="create another local account")
    create_user.add_argument("--username", required=True)
    create_user.add_argument("--role", choices=("admin", "user"), default="user")
    create_user.add_argument("--password-env")

    commands.add_parser("list-users", help="list non-secret account metadata")

    for command in ("enable-user", "disable-user"):
        target = commands.add_parser(command)
        target.add_argument("--username", required=True)

    reset = commands.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    reset.add_argument("--password-env")
    return value


def password_from(args) -> str:
    if args.password_env:
        password = os.environ.pop(args.password_env, "")
        if not password:
            raise ValueError(f"password environment variable {args.password_env} is empty")
        return password
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("password confirmation does not match")
    return first


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    state_dir = Path(args.state_dir).expanduser().absolute()
    database = Database(state_dir / "notifinho.db")
    version = database.migrate()
    if args.command == "init":
        print(f"state_schema={version}")
        print(f"database={database.path}")
        return 0

    users = UserStore(database)
    if args.command == "create-admin":
        user = users.bootstrap_admin(args.username, password_from(args))
        print("account_created=admin")
        print(f"username={user.username}")
        print(f"user_id={user.id}")
        return 0
    if args.command == "create-user":
        user = users.create(args.username, password_from(args), role=args.role)
        print(f"account_created={user.role}")
        print(f"username={user.username}")
        print(f"user_id={user.id}")
        return 0
    if args.command == "list-users":
        for user in users.list():
            locked = user.locked_until is not None and user.locked_until > int(time.time())
            print(
                f"{user.username}\trole={user.role}\tenabled={str(user.enabled).lower()}"
                f"\tlocked={str(locked).lower()}\tid={user.id}"
            )
        return 0

    user = users.get_by_username(args.username)
    if args.command == "enable-user":
        users.set_enabled(user.id, True)
        print(f"account_enabled={user.username}")
        return 0
    if args.command == "disable-user":
        users.set_enabled(user.id, False)
        print(f"account_disabled={user.username}")
        return 0
    if args.command == "reset-password":
        users.reset_password(user.id, password_from(args))
        print(f"password_reset={user.username}")
        return 0
    raise RuntimeError("unsupported command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, PermissionError, RuntimeError, ValueError) as error:
        print(f"error={error}", file=sys.stderr)
        raise SystemExit(1) from None
