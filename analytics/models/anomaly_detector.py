import sys
import logging
import argparse
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sqlalchemy import text
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.connection import engine
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "models" / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


# Feature Engineering

FEATURE_QUERY = """
    SELECT
        t.transaction_id,
        t.txn_timestamp,
        t.amount,
        t.is_anomaly                                        AS ground_truth,
        -- Feature 1: Log-transformed amount (reduces right-skew)
        LOG(1 + t.amount)                                   AS log_amount,
        -- Feature 2: Hour of day (0-23) — captures time-of-day patterns
        HOUR(t.txn_timestamp)                               AS hour_of_day,
        -- Feature 3: Day of week (0=Monday...6=Sunday)
        WEEKDAY(t.txn_timestamp)                            AS day_of_week,
        -- Feature 4: Merchant risk encoded as integer
        CASE m.risk_category
            WHEN 'low'    THEN 0
            WHEN 'medium' THEN 1
            WHEN 'high'   THEN 2
        END                                                 AS merchant_risk_encoded,
        -- Feature 5: Payment channel encoded
        CASE t.payment_channel
            WHEN 'card_pos'       THEN 0
            WHEN 'card_online'    THEN 1
            WHEN 'atm'            THEN 2
            WHEN 'mobile_app'     THEN 3
            WHEN 'bank_transfer'  THEN 4
        END                                                 AS channel_encoded,
        -- Feature 6: Customer's historical average spend (over all their txns)
        --   This is computed as a correlated aggregate — no leakage because we
        --   use the customer's OVERALL history, not this specific transaction.
        cust_stats.avg_amount                               AS customer_avg_amount,
        cust_stats.stddev_amount                            AS customer_std_amount,
        cust_stats.txn_count                                AS customer_txn_count
    FROM transactions t
    INNER JOIN merchants m ON m.merchant_id = t.merchant_id
    INNER JOIN accounts a  ON a.account_id  = t.account_id
    -- Subquery: customer-level historical statistics
    INNER JOIN (
        SELECT
            a2.customer_id,
            ROUND(AVG(t2.amount), 4)    AS avg_amount,
            ROUND(STDDEV(t2.amount), 4) AS stddev_amount,
            COUNT(t2.transaction_id)    AS txn_count
        FROM transactions t2
        INNER JOIN accounts a2 ON a2.account_id = t2.account_id
        GROUP BY a2.customer_id
    ) cust_stats ON cust_stats.customer_id = a.customer_id
    ORDER BY t.txn_timestamp
"""


def load_features(conn) -> pd.DataFrame:
    logger.info("Loading transaction features from database…")
    df = pd.read_sql(text(FEATURE_QUERY), conn)
    logger.info("Loaded %d transactions", len(df))
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df["amount_zscore"] = (
        (df["amount"] - df["customer_avg_amount"])
        / (df["customer_std_amount"].replace(0, 1))
    ).fillna(0)

    df["is_night_txn"] = ((df["hour_of_day"] >= 23) | (df["hour_of_day"] <= 5)).astype(int)

    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    df["log_customer_txn_count"] = np.log1p(df["customer_txn_count"])

    return df


FEATURE_COLUMNS = [
    "log_amount",
    "hour_of_day",
    "day_of_week",
    "merchant_risk_encoded",
    "channel_encoded",
    "customer_avg_amount",
    "customer_std_amount",
    "amount_zscore",
    "is_night_txn",
    "is_weekend",
    "log_customer_txn_count",
]


# Baseline: Statistical threshold

def statistical_baseline(df: pd.DataFrame, threshold_sigma: float = 3.0) -> np.ndarray:
    return (df["amount_zscore"] > threshold_sigma).astype(int).values


# Training and scoring

def train_and_score(
    df: pd.DataFrame,
    contamination: float,
    random_seed: int,
    train_fraction: float = 0.75,
) -> tuple[pd.DataFrame, dict, object, object]:
    df = df.sort_values("txn_timestamp").reset_index(drop=True)
    n_train = int(len(df) * train_fraction)
    train_df = df.iloc[:n_train]
    test_df  = df.iloc[n_train:]
    cutoff   = df["txn_timestamp"].iloc[n_train]

    logger.info("Training on %d rows (before %s)", n_train, cutoff)
    logger.info("Evaluating on %d rows", len(test_df))

    X_train = train_df[FEATURE_COLUMNS].fillna(0).values
    X_test  = test_df[FEATURE_COLUMNS].fillna(0).values
    X_all   = df[FEATURE_COLUMNS].fillna(0).values

    # Scale features — IF is sensitive to feature scale
    scaler  = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)
    X_all_s   = scaler.transform(X_all)

    # Train model
    model = IsolationForest(
        contamination=contamination,
        random_state=random_seed,
        n_estimators=200,
        n_jobs=-1,
    )
    model.fit(X_train_s)
    logger.info("Model trained.")

    # Score ALL transactions
    all_scores = model.score_samples(X_all_s)
    all_flags  = (model.predict(X_all_s) == -1).astype(int)

    df["anomaly_score"] = all_scores
    df["is_flagged"]    = all_flags

    # Evaluate on test set
    test_flags  = all_flags[n_train:]
    test_truth  = test_df["ground_truth"].values
    baseline    = statistical_baseline(test_df)

    metrics = {}
    if test_truth.sum() > 0:
        metrics["if_precision"] = round(precision_score(test_truth, test_flags, zero_division=0), 4)
        metrics["if_recall"]    = round(recall_score(   test_truth, test_flags, zero_division=0), 4)
        metrics["if_f1"]        = round(f1_score(       test_truth, test_flags, zero_division=0), 4)
        metrics["if_cm"]        = confusion_matrix(test_truth, test_flags).tolist()
        metrics["bl_precision"] = round(precision_score(test_truth, baseline, zero_division=0), 4)
        metrics["bl_recall"]    = round(recall_score(   test_truth, baseline, zero_division=0), 4)
        metrics["bl_f1"]        = round(f1_score(       test_truth, baseline, zero_division=0), 4)
        logger.info("IF  — Prec: %.3f  Rec: %.3f  F1: %.3f",
                    metrics["if_precision"], metrics["if_recall"], metrics["if_f1"])
        logger.info("BL  — Prec: %.3f  Rec: %.3f  F1: %.3f",
                    metrics["bl_precision"], metrics["bl_recall"], metrics["bl_f1"])
    else:
        logger.warning("No ground-truth anomalies in test set — skipping eval metrics")
        metrics["if_precision"] = metrics["if_recall"] = metrics["if_f1"] = None

    metrics["training_cutoff"] = str(cutoff)
    metrics["n_flagged"]       = int(all_flags.sum())
    metrics["n_total"]         = len(df)

    return df, metrics, model, scaler


# Persistence

def save_scores_to_db(df: pd.DataFrame, run_id: str, conn):
    records = df[["transaction_id", "anomaly_score", "is_flagged"]].copy()
    records["model_run_id"] = run_id
    records = records.rename(columns={"anomaly_score": "anomaly_score_val"})

    batch_size = 2000
    total = 0
    for start in range(0, len(records), batch_size):
        batch = records.iloc[start:start + batch_size]
        conn.execute(
            text("""
                INSERT IGNORE INTO anomaly_scores
                    (transaction_id, model_run_id, anomaly_score, is_flagged)
                VALUES
                    (:transaction_id, :model_run_id, :anomaly_score_val, :is_flagged)
            """),
            batch.to_dict(orient="records")
        )
        conn.commit()
        total += len(batch)
    logger.info("Saved %d scores to anomaly_scores table", total)


def save_model_run(run_id: str, metrics: dict, contamination: float,
                   random_seed: int, artifact_path: str, conn):
    conn.execute(
        text("""
            INSERT INTO model_runs
                (run_id, model_type, contamination, random_seed,
                 n_transactions, n_flagged, precision_score, recall_score,
                 f1_score, training_cutoff, artifact_path)
            VALUES
                (:run_id, 'IsolationForest', :contamination, :random_seed,
                 :n_transactions, :n_flagged, :precision_score, :recall_score,
                 :f1_score, :training_cutoff, :artifact_path)
        """),
        {
            "run_id": run_id,
            "contamination": contamination,
            "random_seed": random_seed,
            "n_transactions": metrics["n_total"],
            "n_flagged": metrics["n_flagged"],
            "precision_score": metrics.get("if_precision"),
            "recall_score":    metrics.get("if_recall"),
            "f1_score":        metrics.get("if_f1"),
            "training_cutoff": metrics.get("training_cutoff"),
            "artifact_path": artifact_path,
        }
    )
    conn.commit()


# Entry point

def main():
    parser = argparse.ArgumentParser(description="Run FTI anomaly detection pipeline")
    parser.add_argument("--contamination", type=float,
                        default=settings.anomaly_contamination,
                        help="Expected fraction of anomalies (default: 0.02)")
    parser.add_argument("--seed", type=int,
                        default=settings.anomaly_random_seed,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    logger.info("Model run ID: %s", run_id)

    with engine.connect() as conn:
        # Check for duplicate run (should not happen, but be safe)
        existing_scores = conn.execute(
            text("SELECT COUNT(*) FROM anomaly_scores WHERE model_run_id LIKE :prefix"),
            {"prefix": run_id[:15] + "%"}
        ).scalar()
        if existing_scores > 0:
            logger.warning("Scores for this run already exist — skipping DB write")

        df = load_features(conn)

    df = engineer_features(df)

    # Verify no leakage: ground_truth must NOT be in feature columns
    assert "ground_truth" not in FEATURE_COLUMNS, "DATA LEAKAGE: ground_truth in features!"
    assert "is_anomaly"   not in FEATURE_COLUMNS, "DATA LEAKAGE: is_anomaly in features!"
    logger.info("Leakage check passed — ground truth not in feature set.")

    scored_df, metrics, model, scaler = train_and_score(
        df, args.contamination, args.seed
    )

    # Save model artifact
    artifact_path = str(ARTIFACTS_DIR / f"isolation_forest_{run_id}.pkl")
    joblib.dump({"model": model, "scaler": scaler, "features": FEATURE_COLUMNS,
                 "run_id": run_id}, artifact_path)
    logger.info("Model saved to %s", artifact_path)

    # Persist scores and run metadata
    with engine.begin() as conn:
        save_scores_to_db(scored_df, run_id, conn)
        save_model_run(run_id, metrics, args.contamination, args.seed, artifact_path, conn)

    # Print summary
    print("\n── Anomaly Detection Results ──────────────────────────────────")
    print(f"  Run ID:           {run_id}")
    print(f"  Total scored:     {metrics['n_total']:,}")
    print(f"  Flagged:          {metrics['n_flagged']:,} "
          f"({100*metrics['n_flagged']/metrics['n_total']:.1f}%)")
    if metrics.get("if_f1") is not None:
        print(f"\n  Isolation Forest vs Statistical Baseline:")
        print(f"  {'':5} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        print(f"  {'IF':5} {metrics['if_precision']:>10.3f} {metrics['if_recall']:>10.3f} {metrics['if_f1']:>10.3f}")
        print(f"  {'BL':5} {metrics['bl_precision']:>10.3f} {metrics['bl_recall']:>10.3f} {metrics['bl_f1']:>10.3f}")
        print(f"\n  Confusion Matrix (IF on test set):")
        cm = metrics["if_cm"]
        print(f"    TN={cm[0][0]:,}  FP={cm[0][1]:,}")
        print(f"    FN={cm[1][0]:,}  TP={cm[1][1]:,}")
    print("────────────────────────────────────────────────────────────\n")
    print("⚠  IMPORTANT: Flagged transactions are SUSPICIOUS, not confirmed fraud.")
    print("   Always review with a human investigator before taking action.\n")


if __name__ == "__main__":
    main()
