import sys
import logging
import argparse
import random
from datetime import datetime, timedelta, date
from pathlib import Path

import numpy as np
from faker import Faker
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.connection import engine
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Configuration
RANDOM_SEED        = 42
N_CUSTOMERS        = 10_000
N_ACCOUNTS         = 15_000
N_MERCHANTS        = 100
N_TRANSACTIONS     = 100_000
ANOMALY_FRACTION   = 0.02       # ~2 000 anomalies injected
BATCH_SIZE         = 2_000
START_DATE         = date(2023, 1, 1)
END_DATE           = date(2024, 12, 31)

fake = Faker()
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# Reference data
SEGMENTS = ["retail", "premium", "business", "vip"]
SEGMENT_WEIGHTS = [0.55, 0.25, 0.15, 0.05]

ACCOUNT_TYPES = ["checking", "savings", "business", "investment"]
ACCOUNT_TYPE_WEIGHTS = [0.45, 0.30, 0.15, 0.10]

CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "SGD", "INR"]
CURRENCY_WEIGHTS = [0.50, 0.20, 0.10, 0.08, 0.06, 0.04, 0.02]

COUNTRIES = [
    "United States", "United Kingdom", "Germany", "Canada", "Australia",
    "Singapore", "India", "France", "Netherlands", "Japan",
    "Brazil", "Mexico", "South Africa", "UAE", "Hong Kong"
]
COUNTRY_WEIGHTS = [0.35, 0.12, 0.08, 0.07, 0.06, 0.05, 0.05, 0.05,
                   0.04, 0.04, 0.03, 0.02, 0.01, 0.01, 0.02]

TXN_TYPES = ["purchase", "refund", "transfer", "withdrawal", "deposit"]
TXN_TYPE_WEIGHTS = [0.65, 0.08, 0.12, 0.08, 0.07]

CHANNELS = ["card_online", "card_pos", "bank_transfer", "mobile_app", "atm"]
CHANNEL_WEIGHTS = [0.35, 0.30, 0.15, 0.15, 0.05]

STATUSES = ["completed", "failed", "pending", "reversed"]
STATUS_WEIGHTS = [0.88, 0.06, 0.04, 0.02]

RISK_CATEGORIES = ["low", "medium", "high"]
RISK_WEIGHTS = [0.60, 0.30, 0.10]

CATEGORIES = [
    ("Groceries",           "Supermarkets and food stores"),
    ("Dining & Restaurants","Restaurants, cafes, and fast food"),
    ("Travel",              "Flights, hotels, and travel agencies"),
    ("Entertainment",       "Streaming, cinema, and events"),
    ("Shopping",            "Retail stores and online shopping"),
    ("Healthcare",          "Pharmacies, clinics, and hospitals"),
    ("Utilities",           "Electricity, water, and internet bills"),
    ("Fuel & Transport",    "Petrol stations and public transport"),
    ("ATM Withdrawal",      "Cash withdrawals at ATMs"),
    ("Bank Transfer",       "Inter-bank and wire transfers"),
    ("Insurance",           "Insurance premium payments"),
    ("Education",           "Tuition, books, and online courses"),
    ("Subscriptions",       "Recurring software or media subscriptions"),
    ("Charity & Donations", "Charitable contributions"),
    ("Gaming",              "Video games and in-app purchases"),
    ("Home & Garden",       "Home improvement and gardening"),
    ("Automotive",          "Car maintenance and repairs"),
    ("Investments",         "Brokerage and investment platform fees"),
    ("Payroll",             "Salary and wage deposits"),
    ("Rent & Mortgage",     "Rental and mortgage payments"),
    ("Taxes",               "Government tax payments"),
    ("Foreign Exchange",    "Currency conversion transactions"),
    ("Cryptocurrency",      "Crypto exchange transactions"),
    ("High-Risk Transfer",  "Transfers flagged as high-risk corridors"),
]

MERCHANT_CATEGORIES = [cat[0] for cat in CATEGORIES]

HIGH_RISK_COUNTRIES = ["Russia", "Iran", "North Korea", "Myanmar", "Venezuela"]


# Helpers

def random_date(start: date, end: date) -> datetime:
    delta = (end - start).days
    d = start + timedelta(days=random.randint(0, delta))
    hour = int(np.random.choice(range(24), p=_hour_weights()))
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return datetime(d.year, d.month, d.day, hour, minute, second)


def _hour_weights():
    """Business hours get more traffic; late night gets very little."""
    weights = np.array([
        0.5, 0.3, 0.2, 0.2, 0.3, 0.8,   # 0-5
        1.5, 3.0, 4.5, 5.5, 6.0, 6.5,   # 6-11
        7.0, 7.5, 7.0, 6.5, 5.5, 6.0,   # 12-17
        7.5, 8.0, 7.0, 5.0, 3.0, 1.5,   # 18-23
    ], dtype=float)
    return weights / weights.sum()


def weighted_choice(options, weights):
    return random.choices(options, weights=weights, k=1)[0]


def normal_amount(segment: str) -> float:
    """Realistic spending amounts by customer segment."""
    params = {
        "retail":   (50,   80),
        "premium":  (200,  300),
        "business": (800,  1200),
        "vip":      (3000, 5000),
    }
    mu, sigma = params[segment]
    val = abs(np.random.normal(mu, sigma * 0.4))
    return round(max(1.0, val), 2)


def show_counts(conn):
    tables = ["customers", "accounts", "merchants", "categories",
              "transactions", "anomaly_scores", "model_runs"]
    print("\n── Current Row Counts ─────────────────────────────────────────")
    for t in tables:
        try:
            n = conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
            print(f"  {t:<20} {n:>10,}")
        except Exception:
            print(f"  {t:<20} (table not found)")
    print("────────────────────────────────────────────────────────────\n")


# Main generation functions

def generate_categories(conn) -> list[int]:
    logger.info("Inserting %d categories…", len(CATEGORIES))
    ids = []
    for name, desc in CATEGORIES:
        result = conn.execute(
            text("INSERT IGNORE INTO categories (category_name, description) VALUES (:n, :d)"),
            {"n": name, "d": desc}
        )
        # Get the id whether inserted or already existing
        row = conn.execute(
            text("SELECT category_id FROM categories WHERE category_name = :n"),
            {"n": name}
        ).fetchone()
        ids.append(row.category_id)
    conn.commit()
    logger.info("Categories ready: %d", len(ids))
    return ids


def generate_merchants(conn) -> list[dict]:
    logger.info("Inserting %d merchants…", N_MERCHANTS)
    merchants = []
    for i in range(N_MERCHANTS):
        cat = weighted_choice(MERCHANT_CATEGORIES, [1] * len(MERCHANT_CATEGORIES))
        country = weighted_choice(COUNTRIES, COUNTRY_WEIGHTS)
        risk = weighted_choice(RISK_CATEGORIES, RISK_WEIGHTS)
        name = fake.company()
        conn.execute(
            text("""
                INSERT IGNORE INTO merchants
                    (merchant_name, merchant_category, country, risk_category)
                VALUES (:name, :cat, :country, :risk)
            """),
            {"name": name, "cat": cat, "country": country, "risk": risk}
        )
        row = conn.execute(
            text("SELECT merchant_id FROM merchants WHERE merchant_name = :n"),
            {"n": name}
        ).fetchone()
        merchants.append({
            "merchant_id": row.merchant_id,
            "category": cat,
            "country": country,
            "risk": risk
        })
    conn.commit()
    # Re-fetch all to ensure we have the real IDs
    rows = conn.execute(text("SELECT merchant_id, merchant_category, country, risk_category FROM merchants")).fetchall()
    result = [{"merchant_id": r.merchant_id, "category": r.merchant_category,
               "country": r.country, "risk": r.risk_category} for r in rows]
    logger.info("Merchants ready: %d", len(result))
    return result


def generate_customers(conn) -> list[dict]:
    logger.info("Inserting %d customers in batches…", N_CUSTOMERS)
    customers = []
    emails_used = set()

    for batch_start in range(0, N_CUSTOMERS, BATCH_SIZE):
        batch = []
        for _ in range(min(BATCH_SIZE, N_CUSTOMERS - batch_start)):
            email = fake.unique.email()
            segment = weighted_choice(SEGMENTS, SEGMENT_WEIGHTS)
            country = weighted_choice(COUNTRIES, COUNTRY_WEIGHTS)
            signup = fake.date_between(start_date="-5y", end_date="-6m")
            batch.append({
                "full_name": fake.name(),
                "email": email,
                "signup_date": signup,
                "country": country,
                "segment": segment,
                "account_status": weighted_choice(
                    ["active", "inactive", "suspended"], [0.88, 0.08, 0.04]
                )
            })

        conn.execute(
            text("""
                INSERT IGNORE INTO customers
                    (full_name, email, signup_date, country, segment, account_status)
                VALUES
                    (:full_name, :email, :signup_date, :country, :segment, :account_status)
            """),
            batch
        )
        conn.commit()
        logger.info("  Customers batch done: %d/%d", batch_start + len(batch), N_CUSTOMERS)

    rows = conn.execute(
        text("SELECT customer_id, segment, country FROM customers")
    ).fetchall()
    customers = [{"customer_id": r.customer_id, "segment": r.segment, "country": r.country} for r in rows]
    logger.info("Customers ready: %d", len(customers))
    return customers


def generate_accounts(conn, customers: list[dict]) -> list[dict]:
    logger.info("Inserting %d accounts…", N_ACCOUNTS)
    accounts = []

    # Distribute accounts across customers — some customers have multiple
    customer_ids = [c["customer_id"] for c in customers]
    customer_map = {c["customer_id"]: c for c in customers}

    assigned = []
    for i in range(N_ACCOUNTS):
        cid = random.choice(customer_ids)
        atype = weighted_choice(ACCOUNT_TYPES, ACCOUNT_TYPE_WEIGHTS)
        currency = weighted_choice(CURRENCIES, CURRENCY_WEIGHTS)
        opening = fake.date_between(start_date="-4y", end_date="-3m")
        assigned.append({
            "customer_id": cid,
            "account_type": atype,
            "currency": currency,
            "account_status": weighted_choice(
                ["active", "dormant", "closed"], [0.80, 0.15, 0.05]
            ),
            "opening_date": opening,
        })

    for batch_start in range(0, len(assigned), BATCH_SIZE):
        batch = assigned[batch_start:batch_start + BATCH_SIZE]
        conn.execute(
            text("""
                INSERT INTO accounts
                    (customer_id, account_type, currency, account_status, opening_date)
                VALUES
                    (:customer_id, :account_type, :currency, :account_status, :opening_date)
            """),
            batch
        )
        conn.commit()
        logger.info("  Accounts batch done: %d/%d", batch_start + len(batch), N_ACCOUNTS)

    rows = conn.execute(
        text("""
            SELECT a.account_id, a.customer_id, a.currency,
                   c.segment, c.country
            FROM accounts a
            JOIN customers c ON a.customer_id = c.customer_id
        """)
    ).fetchall()
    result = [
        {
            "account_id": r.account_id,
            "customer_id": r.customer_id,
            "currency": r.currency,
            "segment": r.segment,
            "country": r.country,
        }
        for r in rows
    ]
    logger.info("Accounts ready: %d", len(result))
    return result


def generate_transactions(conn, accounts: list[dict], merchants: list[dict],
                           category_ids: list[int]) -> None:
    logger.info("Inserting %d transactions in batches…", N_TRANSACTIONS)

    n_anomaly = int(N_TRANSACTIONS * ANOMALY_FRACTION)
    n_normal  = N_TRANSACTIONS - n_anomaly

    # ── Normal transactions ────────────────────────────────────────────────────
    logger.info("  Generating %d normal transactions…", n_normal)
    batch = []
    for i in range(n_normal):
        acc = random.choice(accounts)
        merch = random.choice(merchants)
        cat_id = random.choice(category_ids)
        amount = normal_amount(acc["segment"])
        ts = random_date(START_DATE, END_DATE)
        batch.append({
            "account_id": acc["account_id"],
            "merchant_id": merch["merchant_id"],
            "category_id": cat_id,
            "txn_timestamp": ts,
            "amount": amount,
            "currency": acc["currency"],
            "txn_type": weighted_choice(TXN_TYPES, TXN_TYPE_WEIGHTS),
            "payment_channel": weighted_choice(CHANNELS, CHANNEL_WEIGHTS),
            "txn_status": weighted_choice(STATUSES, STATUS_WEIGHTS),
            "country": acc["country"],
            "is_anomaly": 0,
            "anomaly_type": None,
        })

        if len(batch) >= BATCH_SIZE:
            _insert_transactions(conn, batch)
            logger.info("  Transactions inserted: %d/%d", i + 1, N_TRANSACTIONS)
            batch = []

    if batch:
        _insert_transactions(conn, batch)

    # Anomalous transactions
    logger.info("  Injecting %d anomalies…", n_anomaly)
    anomaly_batch = []
    high_risk_merchants = [m for m in merchants if m["risk"] == "high"]
    if not high_risk_merchants:
        high_risk_merchants = merchants[:5]

    # Split anomalies across 5 types roughly equally
    type_quota = n_anomaly // 5
    remainder  = n_anomaly - type_quota * 5

    # 1. Large amount anomalies
    for _ in range(type_quota):
        acc = random.choice(accounts)
        merch = random.choice(merchants)
        cat_id = random.choice(category_ids)
        base = normal_amount(acc["segment"])
        amount = round(base * random.uniform(10, 50), 2)
        ts = random_date(START_DATE, END_DATE)
        anomaly_batch.append({
            "account_id": acc["account_id"],
            "merchant_id": merch["merchant_id"],
            "category_id": cat_id,
            "txn_timestamp": ts,
            "amount": amount,
            "currency": acc["currency"],
            "txn_type": "purchase",
            "payment_channel": weighted_choice(CHANNELS, CHANNEL_WEIGHTS),
            "txn_status": "completed",
            "country": acc["country"],
            "is_anomaly": 1,
            "anomaly_type": "large_amount",
        })

    # 2. Velocity burst (5 txns within 10 minutes for same account)
    for _ in range(type_quota):
        acc = random.choice(accounts)
        base_ts = random_date(START_DATE, END_DATE)
        for j in range(5):
            ts = base_ts + timedelta(minutes=j * 2)
            merch = random.choice(merchants)
            anomaly_batch.append({
                "account_id": acc["account_id"],
                "merchant_id": merch["merchant_id"],
                "category_id": random.choice(category_ids),
                "txn_timestamp": ts,
                "amount": round(random.uniform(50, 500), 2),
                "currency": acc["currency"],
                "txn_type": "purchase",
                "payment_channel": "card_online",
                "txn_status": "completed",
                "country": acc["country"],
                "is_anomaly": 1,
                "anomaly_type": "velocity_burst",
            })

    # 3. Unusual hour (02:00–04:00)
    for _ in range(type_quota):
        acc = random.choice(accounts)
        merch = random.choice(merchants)
        d = fake.date_between(start_date=START_DATE, end_date=END_DATE)
        ts = datetime(d.year, d.month, d.day, random.randint(2, 3),
                      random.randint(0, 59), random.randint(0, 59))
        anomaly_batch.append({
            "account_id": acc["account_id"],
            "merchant_id": merch["merchant_id"],
            "category_id": random.choice(category_ids),
            "txn_timestamp": ts,
            "amount": round(random.uniform(200, 2000), 2),
            "currency": acc["currency"],
            "txn_type": "purchase",
            "payment_channel": "card_online",
            "txn_status": "completed",
            "country": acc["country"],
            "is_anomaly": 1,
            "anomaly_type": "unusual_hour",
        })

    # 4. Foreign high-risk merchant
    for _ in range(type_quota):
        acc = random.choice(accounts)
        merch = random.choice(high_risk_merchants)
        ts = random_date(START_DATE, END_DATE)
        anomaly_batch.append({
            "account_id": acc["account_id"],
            "merchant_id": merch["merchant_id"],
            "category_id": random.choice(category_ids),
            "txn_timestamp": ts,
            "amount": round(random.uniform(500, 5000), 2),
            "currency": acc["currency"],
            "txn_type": "transfer",
            "payment_channel": "bank_transfer",
            "txn_status": "completed",
            "country": random.choice(HIGH_RISK_COUNTRIES),
            "is_anomaly": 1,
            "anomaly_type": "foreign_high_risk",
        })

    # 5. Pattern shift (spike after low-activity period) + remainder
    for _ in range(type_quota + remainder):
        acc = random.choice(accounts)
        merch = random.choice(merchants)
        # Pick a date in the last 3 months of the period (sudden spike)
        ts = random_date(date(2024, 10, 1), END_DATE)
        amount = normal_amount(acc["segment"]) * random.uniform(8, 30)
        anomaly_batch.append({
            "account_id": acc["account_id"],
            "merchant_id": merch["merchant_id"],
            "category_id": random.choice(category_ids),
            "txn_timestamp": ts,
            "amount": round(amount, 2),
            "currency": acc["currency"],
            "txn_type": "purchase",
            "payment_channel": weighted_choice(CHANNELS, CHANNEL_WEIGHTS),
            "txn_status": "completed",
            "country": acc["country"],
            "is_anomaly": 1,
            "anomaly_type": "pattern_shift",
        })

    for b_start in range(0, len(anomaly_batch), BATCH_SIZE):
        _insert_transactions(conn, anomaly_batch[b_start:b_start + BATCH_SIZE])

    logger.info("  Anomaly injection complete: %d records", len(anomaly_batch))


def _insert_transactions(conn, batch: list[dict]):
    conn.execute(
        text("""
            INSERT INTO transactions
                (account_id, merchant_id, category_id, txn_timestamp, amount,
                 currency, txn_type, payment_channel, txn_status, country,
                 is_anomaly, anomaly_type)
            VALUES
                (:account_id, :merchant_id, :category_id, :txn_timestamp, :amount,
                 :currency, :txn_type, :payment_channel, :txn_status, :country,
                 :is_anomaly, :anomaly_type)
        """),
        batch
    )
    conn.commit()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate FTI synthetic data")
    parser.add_argument("--reset",  action="store_true",
                        help="Delete all data and regenerate from scratch")
    parser.add_argument("--counts", action="store_true",
                        help="Show current row counts and exit")
    args = parser.parse_args()

    with engine.begin() as conn:
        if args.counts:
            show_counts(conn)
            return

        # Check for existing data
        existing = conn.execute(
            text("SELECT COUNT(*) FROM transactions")
        ).scalar()

        if args.counts:
            show_counts(conn)
            return

        if existing > 0 and not args.reset:
            print(f"\n⚠  Transactions table already has {existing:,} rows.")
            print("   Pass --reset to delete all data and regenerate.")
            print("   Pass --counts to just view current counts.\n")
            sys.exit(0)

        if args.reset and existing > 0:
            logger.warning("--reset: deleting all data from all tables…")
            # Disable FK checks to allow truncation in any order
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for t in ["anomaly_scores", "model_runs", "transactions",
                      "accounts", "merchants", "customers", "categories"]:
                conn.execute(text(f"TRUNCATE TABLE `{t}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            conn.commit()
            logger.info("All tables cleared.")

    # Generation pipeline
    start_time = datetime.now()

    with engine.begin() as conn:
        category_ids = generate_categories(conn)

    with engine.begin() as conn:
        merchants = generate_merchants(conn)

    with engine.begin() as conn:
        customers = generate_customers(conn)

    with engine.begin() as conn:
        accounts = generate_accounts(conn, customers)

    with engine.begin() as conn:
        generate_transactions(conn, accounts, merchants, category_ids)

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("Data generation complete in %.1f seconds.", elapsed)

    with engine.connect() as conn:
        show_counts(conn)


if __name__ == "__main__":
    main()
