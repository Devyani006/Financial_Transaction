"""
scripts/setup_schema.py — Database Schema Initialization
=========================================================
Run this FIRST before seeding data.

Why idempotent?
  CREATE TABLE IF NOT EXISTS means running this script twice is safe — it will
  not drop or alter existing tables. If a table already has data, nothing
  changes. This lets you re-run setup without fear.

Usage:
  python scripts/setup_schema.py
  python scripts/setup_schema.py --force-check   # verifies existing tables
"""

import sys
import logging
import argparse
from pathlib import Path
from sqlalchemy import text, inspect

# Add project root to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.connection import engine, check_connectivity
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).parent.parent / "sql" / "schema.sql"

EXPECTED_TABLES = [
    "customers", "accounts", "merchants", "categories",
    "transactions", "anomaly_scores", "model_runs"
]


def run_schema():
    """Execute the schema SQL file against the configured database."""
    logger.info("Reading schema from %s", SCHEMA_FILE)
    sql_content = SCHEMA_FILE.read_text(encoding="utf-8")

    # Split on semicolons to execute statements one at a time.
    # We skip blank statements and comment-only blocks.
    statements = [
        stmt.strip()
        for stmt in sql_content.split(";")
        if stmt.strip() and not stmt.strip().startswith("--")
    ]

    with engine.begin() as conn:
        for stmt in statements:
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception as e:
                    # Log but continue — some statements (like USE) may behave
                    # differently depending on permissions
                    logger.warning("Statement skipped (%s): %s...", e, stmt[:60])

    logger.info("Schema execution complete.")


def verify_tables():
    """Check that all expected tables exist and report their row counts."""
    inspector = inspect(engine)
    existing = inspector.get_table_names()

    print("\n── Table Verification ─────────────────────────────────────────")
    all_ok = True
    with engine.connect() as conn:
        for table in EXPECTED_TABLES:
            if table in existing:
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM `{table}`")
                ).scalar()
                print(f"  ✓  {table:<20} {count:>10,} rows")
            else:
                print(f"  ✗  {table:<20} MISSING")
                all_ok = False

    if all_ok:
        print("\n  All expected tables are present.")
    else:
        print("\n  Some tables are missing — re-run setup_schema.py")
    print("──────────────────────────────────────────────────────────────\n")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Initialize FTI database schema")
    parser.add_argument(
        "--force-check", action="store_true",
        help="Only verify existing tables, do not run schema SQL"
    )
    args = parser.parse_args()

    # Always check connectivity first
    logger.info("Checking database connectivity…")
    health = check_connectivity()
    if health["status"] != "ok":
        logger.error("Cannot connect to MySQL: %s", health.get("detail"))
        sys.exit(1)
    logger.info("Connected to MySQL %s", health["mysql_version"])
    logger.info("Database: %s  User: %s", settings.db.name, settings.db.user)

    if not args.force_check:
        run_schema()

    verify_tables()


if __name__ == "__main__":
    main()
