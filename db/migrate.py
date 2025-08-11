from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List

import psycopg

from . import MIGRATIONS_DIR
from dotenv import load_dotenv


# Load environment variables from .env so DATABASE_URL is available when running via CLI
load_dotenv()


def _ensure_schema_migrations(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version TEXT PRIMARY KEY,
              applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return {row[0] for row in cur.fetchall()}


def _list_migration_files() -> List[Path]:
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_all(conn: psycopg.Connection) -> None:
    _ensure_schema_migrations(conn)
    applied = _applied_versions(conn)
    for path in _list_migration_files():
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text()
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        print(f"Applied {version}")


def status(conn: psycopg.Connection) -> None:
    _ensure_schema_migrations(conn)
    applied = _applied_versions(conn)
    for path in _list_migration_files():
        version = path.stem
        mark = "[x]" if version in applied else "[ ]"
        print(f"{mark} {version}")


def apply_to(conn: psycopg.Connection, target_version: str) -> None:
    _ensure_schema_migrations(conn)
    applied = _applied_versions(conn)
    for path in _list_migration_files():
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text()
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        print(f"Applied {version}")
        if version == target_version:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple SQL migrations runner")
    parser.add_argument("command", choices=["up", "status", "to"], help="Migration command")
    parser.add_argument("version", nargs="?", help="Target version for 'to'")
    parser.add_argument("--dsn", dest="dsn", default=os.getenv("DATABASE_URL"), help="Postgres DSN")
    args = parser.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL not set; provide --dsn or set env var")

    # Normalize SQLAlchemy-style URLs (e.g., postgresql+psycopg://) to libpq URL for psycopg
    dsn = args.dsn
    if dsn and "+" in dsn.split("://", 1)[0]:
        # Convert schemes like postgresql+psycopg, postgresql+asyncpg, etc. -> postgresql
        scheme, rest = dsn.split("://", 1)
        base_scheme = scheme.split("+", 1)[0]
        dsn = f"{base_scheme}://{rest}"

    with psycopg.connect(dsn) as conn:
        if args.command == "status":
            status(conn)
        elif args.command == "up":
            apply_all(conn)
        elif args.command == "to":
            if not args.version:
                raise SystemExit("'to' requires a version, e.g., 20250810_init")
            apply_to(conn, args.version)


if __name__ == "__main__":
    main()

