# docs/ER_DIAGRAM.md — Entity-Relationship Diagram

## Database Schema Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   Financial Transaction Intelligence Schema                  │
└──────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐       ┌─────────────────────┐
│    customers    │       │      accounts       │
├─────────────────┤       ├─────────────────────┤
│ PK customer_id  │──────<│ PK account_id       │
│    full_name    │       │ FK customer_id      │
│    email (UQ)   │       │    account_type     │
│    signup_date  │       │    currency         │
│    country      │       │    account_status   │
│    segment      │       │    opening_date     │
│    account_stat │       └──────────┬──────────┘
└─────────────────┘                  │
                                     │ 1:many
                    ┌────────────────▼──────────────────┐
                    │           transactions             │
                    ├───────────────────────────────────┤
                    │ PK transaction_id (BIGINT)        │
                    │ FK account_id                     │
                    │ FK merchant_id                    │
                    │ FK category_id                    │
                    │    txn_timestamp (DATETIME)       │
                    │    amount (DECIMAL 15,2)          │
                    │    currency (CHAR 3)              │
                    │    txn_type                       │
                    │    payment_channel                │
                    │    txn_status                     │
                    │    country                        │
                    │    is_anomaly (TINYINT)           │
                    │    anomaly_type (VARCHAR)         │
                    └──────┬──────────────┬─────────────┘
                           │              │
                    1:many ┘              └ 1:many
                           │              │
          ┌────────────────▼──┐    ┌──────▼──────────────┐
          │     merchants     │    │     categories      │
          ├───────────────────┤    ├─────────────────────┤
          │ PK merchant_id    │    │ PK category_id      │
          │    merchant_name  │    │    category_name(UQ)│
          │    merchant_cat   │    │    description      │
          │    country        │    └─────────────────────┘
          │    risk_category  │
          └───────────────────┘

                    ┌────────────────────────────┐
                    │       anomaly_scores       │
                    ├────────────────────────────┤
                    │ PK score_id                │
                    │ FK transaction_id ─────────┼──► transactions
                    │    model_run_id  (UQ+FK)   │
                    │    anomaly_score (FLOAT)   │
                    │    is_flagged (TINYINT)    │
                    │    scored_at               │
                    └────────────────────────────┘

                    ┌────────────────────────────┐
                    │        model_runs          │
                    ├────────────────────────────┤
                    │ PK run_id (VARCHAR 40)     │
                    │    model_type              │
                    │    contamination           │
                    │    random_seed             │
                    │    n_transactions          │
                    │    n_flagged               │
                    │    precision_score         │
                    │    recall_score            │
                    │    f1_score                │
                    │    training_cutoff         │
                    │    artifact_path           │
                    └────────────────────────────┘
```

## Relationships Explained

| Relationship | Cardinality | Description |
|---|---|---|
| `customers` → `accounts` | One-to-Many | One customer can have multiple accounts (checking + savings) |
| `accounts` → `transactions` | One-to-Many | One account has many transactions over time |
| `merchants` → `transactions` | One-to-Many | One merchant appears in many transactions |
| `categories` → `transactions` | One-to-Many | One category (e.g., Groceries) classifies many transactions |
| `transactions` → `anomaly_scores` | One-to-Many | One transaction can have scores from multiple model runs |

## Why Not Store Customer Attributes on Transactions?

We avoid duplicating `customer.country`, `customer.segment`, etc. in the `transactions` table.

**Reason:** If a customer moves countries, updating `customers.country` fixes it everywhere. If we stored it in every transaction row, we'd have inconsistent historical data.

When we need customer attributes alongside transaction data, SQL JOINs retrieve them efficiently using the indexed `account_id → customer_id` path.

## Index Design Rationale

| Index | Column(s) | Reason |
|---|---|---|
| `idx_txn_timestamp` | `transactions.txn_timestamp` | Most dashboard queries filter by date range |
| `idx_txn_account_time` | `(account_id, txn_timestamp)` | Customer history queries filter by account + time |
| `idx_txn_is_anomaly` | `transactions.is_anomaly` | Anomaly monitoring queries filter on this frequently |
| `idx_txn_status` | `transactions.txn_status` | Status breakdown is a core KPI query |
| `idx_accounts_customer` | `accounts.customer_id` | Every JOIN from transactions → customers passes through this |
| `idx_scores_run` | `anomaly_scores.model_run_id` | Anomaly dashboard groups by run |
| `uq_score_txn_run` | `(transaction_id, model_run_id)` | Prevents duplicate scores per run (unique constraint) |
