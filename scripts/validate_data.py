import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.connection import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# Individual check functions

def check_row_counts(conn) -> list[dict]:
    tables = ["customers", "accounts", "merchants", "categories",
              "transactions", "anomaly_scores", "model_runs"]
    results = []
    for t in tables:
        try:
            n = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            results.append({
                "check": f"row_count_{t}",
                "value": n,
                "status": "PASS" if n > 0 else "WARN",
                "detail": f"{n:,} rows"
            })
        except Exception as e:
            results.append({"check": f"row_count_{t}", "value": 0,
                            "status": "FAIL", "detail": str(e)})
    return results


def check_referential_integrity(conn) -> list[dict]:
    checks = [
        ("orphaned_accounts",
         "SELECT COUNT(*) FROM accounts a LEFT JOIN customers c ON c.customer_id=a.customer_id WHERE c.customer_id IS NULL"),
        ("orphaned_txn_account",
         "SELECT COUNT(*) FROM transactions t LEFT JOIN accounts a ON a.account_id=t.account_id WHERE a.account_id IS NULL"),
        ("orphaned_txn_merchant",
         "SELECT COUNT(*) FROM transactions t LEFT JOIN merchants m ON m.merchant_id=t.merchant_id WHERE m.merchant_id IS NULL"),
        ("orphaned_txn_category",
         "SELECT COUNT(*) FROM transactions t LEFT JOIN categories c ON c.category_id=t.category_id WHERE c.category_id IS NULL"),
    ]
    results = []
    for name, sql in checks:
        count = conn.execute(text(sql)).scalar()
        results.append({
            "check": name,
            "value": count,
            "status": "PASS" if count == 0 else "FAIL",
            "detail": f"{count} orphaned records"
        })
    return results


def check_data_constraints(conn) -> list[dict]:
    checks = [
        ("negative_amounts",
         "SELECT COUNT(*) FROM transactions WHERE amount <= 0",
         "== 0", "All amounts should be positive"),
        ("future_timestamps",
         "SELECT COUNT(*) FROM transactions WHERE txn_timestamp > NOW()",
         "== 0", "No future-dated transactions"),
        ("invalid_currency",
         "SELECT COUNT(*) FROM transactions WHERE currency NOT REGEXP '^[A-Z]{3}$'",
         "== 0", "All currencies should be 3-letter ISO codes"),
        ("anomaly_type_missing",
         "SELECT COUNT(*) FROM transactions WHERE is_anomaly=1 AND (anomaly_type IS NULL OR anomaly_type='')",
         "== 0", "Every anomaly should have a type label"),
        ("duplicate_txn_ids",
         "SELECT COUNT(*) FROM (SELECT transaction_id, COUNT(*) c FROM transactions GROUP BY transaction_id HAVING c > 1) x",
         "== 0", "No duplicate transaction IDs"),
    ]
    results = []
    for name, sql, expected, desc in checks:
        count = conn.execute(text(sql)).scalar()
        status = "PASS" if count == 0 else "FAIL"
        results.append({
            "check": name,
            "value": count,
            "status": status,
            "detail": desc
        })
    return results


def check_amount_distribution(conn) -> list[dict]:
    row = conn.execute(text("""
        SELECT MIN(amount) mn, MAX(amount) mx,
               ROUND(AVG(amount),2) avg_amt,
               COUNT(*) total
        FROM transactions
    """)).fetchone()
    return [{
        "check": "amount_distribution",
        "value": f"min={row.mn}, max={row.mx}, avg={row.avg_amt}",
        "status": "INFO",
        "detail": f"Computed over {row.total:,} transactions"
    }]


def check_anomaly_balance(conn) -> list[dict]:
    row = conn.execute(text("""
        SELECT
            SUM(is_anomaly) anomalies,
            COUNT(*) total,
            ROUND(100.0 * SUM(is_anomaly) / COUNT(*), 2) pct
        FROM transactions
    """)).fetchone()
    status = "PASS" if 0.5 <= row.pct <= 5.0 else "WARN"
    return [{
        "check": "anomaly_balance",
        "value": f"{row.anomalies:,} anomalies ({row.pct}%)",
        "status": status,
        "detail": "Expected 0.5-5% anomaly rate"
    }]


# Report formatting

def format_report(all_checks: list[dict]) -> str:
    lines = [
        "=" * 70,
        " Financial Transaction Intelligence — Data Quality Report",
        f" Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        f"  {'CHECK':<35} {'STATUS':<8} DETAIL",
        "-" * 70,
    ]
    pass_count = fail_count = warn_count = info_count = 0
    for c in all_checks:
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "INFO": "ℹ"}.get(c["status"], "?")
        lines.append(f"  {icon} {c['check']:<33} {c['status']:<8} {c['detail']}")
        if c["status"] == "PASS": pass_count += 1
        elif c["status"] == "FAIL": fail_count += 1
        elif c["status"] == "WARN": warn_count += 1
        else: info_count += 1
    lines += [
        "-" * 70,
        f"  Results: {pass_count} PASS | {fail_count} FAIL | {warn_count} WARN | {info_count} INFO",
        "=" * 70,
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run FTI data quality validation")
    parser.add_argument("--output", help="Save report to this file path")
    args = parser.parse_args()

    logger.info("Running data quality checks…")

    with engine.connect() as conn:
        all_checks = []
        all_checks.extend(check_row_counts(conn))
        all_checks.extend(check_referential_integrity(conn))
        all_checks.extend(check_data_constraints(conn))
        all_checks.extend(check_amount_distribution(conn))
        all_checks.extend(check_anomaly_balance(conn))

    report = format_report(all_checks)
    print("\n" + report)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        logger.info("Report saved to %s", args.output)

    # Exit with error code if any FAIL
    has_fail = any(c["status"] == "FAIL" for c in all_checks)
    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
