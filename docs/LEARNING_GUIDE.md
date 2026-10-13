# docs/LEARNING_GUIDE.md — How FTI Works: A Student Developer's Guide

## Overview

FTI (Financial Transaction Intelligence) is built around five components that all work together:

```
MySQL Database ──► SQL Analytics ──► Python/Pandas ──► FastAPI ──► Streamlit
      │                                    │
      └──────── Anomaly Detection ◄────────┘
```

This guide explains **why** each piece is built the way it is — not just what the code does.

---

## 1. The Database (MySQL)

### Why normalize the schema?

Instead of one giant table with every piece of information, FTI uses five related tables:

```
customers (1) ──── (many) accounts (1) ──── (many) transactions
                                                   ↑           ↑
                               merchants (1) ──────┘     categories (1) ───┘
```

**Why this matters:** If a customer changes their name, you update one row in `customers` — not 100,000 transaction rows. Normalization keeps data consistent and reduces storage.

### Why DECIMAL instead of FLOAT for money?

```sql
-- FLOAT: 19.99 might be stored as 19.990000000000002
-- DECIMAL(15,2): 19.99 is stored as exactly 19.99
```

Financial calculations that accumulate many floating-point errors can produce wrong totals. Banks and payment systems always use exact decimal arithmetic.

### Why parameterized queries?

```python
# DANGEROUS — SQL injection possible:
query = f"SELECT * FROM transactions WHERE status = '{user_input}'"

# SAFE — user input can never alter the query structure:
query = "SELECT * FROM transactions WHERE status = :status"
conn.execute(text(query), {"status": user_input})
```

If a user types `' OR '1'='1` as the status, the parameterized version searches for that exact string — it doesn't break the query logic.

---

## 2. SQL Analytics

The SQL analytics directory demonstrates progressively more advanced techniques:

| File | Technique | Why it matters |
|------|-----------|----------------|
| `01_kpi_overview.sql` | `CASE` expressions | Pivot rows to columns |
| `02_monthly_trends.sql` | `LAG()` window function | Compare to previous period |
| `03_customer_spending_rank.sql` | `RANK()`, `PERCENT_RANK()` | Relative customer value |
| `05_cohort_retention.sql` | CTEs, `PERIOD_DIFF()` | Product stickiness analysis |
| `06_transaction_velocity.sql` | `HAVING` with aggregates | Identify fraud patterns |
| `09_views.sql` | `CREATE VIEW` | DRY principle for complex JOINs |

### What is a CTE?

A CTE (Common Table Expression) is a named subquery you define at the top with `WITH`. It makes complex queries readable:

```sql
-- Without CTE: hard to follow
SELECT * FROM (SELECT customer_id, SUM(amount) AS total FROM ...) AS sub WHERE total > 1000;

-- With CTE: readable
WITH customer_totals AS (
    SELECT customer_id, SUM(amount) AS total FROM ...
)
SELECT * FROM customer_totals WHERE total > 1000;
```

### What is a window function?

Window functions compute values across related rows WITHOUT collapsing them (unlike GROUP BY):

```sql
-- GROUP BY: gives you one row per customer
SELECT customer_id, SUM(amount) FROM transactions GROUP BY customer_id;

-- Window function: gives you the sum BUT keeps all original rows
SELECT customer_id, amount,
       SUM(amount) OVER (PARTITION BY customer_id) AS customer_total
FROM transactions;
```

`LAG(column, 1)` returns the value from the previous row — perfect for month-over-month comparisons.

---

## 3. The Anomaly Detection Model

### Why Isolation Forest?

Isolation Forest works on an intuitive principle: **anomalies are easier to isolate than normal data**.

Imagine playing 20 questions on a dataset:
- A normal transaction needs many yes/no questions to narrow down (e.g., "amount < $100? amount > $50? time is afternoon?...")
- An anomalous $50,000 transaction at 3am is isolated in just a few questions

The algorithm builds hundreds of random "decision trees" and measures the average depth needed to isolate each transaction. Short isolation path = likely anomaly.

### Why chronological train/test split?

```
Jan 2023 ────────────────────── Dec 2024
│                          │              │
└── TRAIN (75%)────────────┘ TEST (25%) ──┘
```

In real fraud detection, you train on past data and predict on future data. A random split would mix future data into training — the model would "know the future," giving unrealistically good results (data leakage).

### Why is class imbalance important?

Only ~2% of transactions are anomalies. A model that always says "not anomaly" would be 98% accurate — but completely useless. We use:

- **Precision**: Of everything I flagged, how many were real anomalies?
- **Recall**: Of all real anomalies, how many did I catch?
- **F1**: Harmonic mean — balances precision and recall

These metrics are meaningful even with imbalanced classes.

### Why keep scores in a separate table?

Model scores go in `anomaly_scores`, not in `transactions`. This means:
- The original transaction data is never modified by model runs
- You can compare different model versions side by side
- Re-running the model doesn't accidentally duplicate results

---

## 4. The FastAPI Backend

### Why FastAPI?

FastAPI is modern Python — it uses type hints you already know from Python 3.6+:

```python
def get_transactions(
    page: int = 1,        # automatically validated as integer
    page_size: int = 25,  # defaults to 25 if not provided
    status: str = None,   # optional filter
) -> TransactionListResponse:  # response is validated before sending
```

FastAPI uses these types to:
1. Validate requests automatically (wrong type → 422 error, not 500 crash)
2. Generate `/docs` OpenAPI documentation automatically
3. Serialize responses without manual `.to_dict()` calls

### Why Pydantic schemas?

Pydantic schemas define what an API response looks like. This prevents accidentally exposing sensitive database fields — you must explicitly list every field in the response model.

### What is dependency injection?

```python
@router.get("/transactions")
def list_transactions(db: Session = Depends(get_db)):  # ← dependency
```

`Depends(get_db)` tells FastAPI: "before calling this function, call `get_db()` and pass its result as `db`." FastAPI handles opening and closing the DB session automatically — even if the function crashes.

---

## 5. The Streamlit Dashboard

### Why query the DB directly instead of going through the API?

The dashboard is an internal analytics tool. Routing all queries through HTTP would add unnecessary overhead for potentially large data transfers. Direct DB access with `@st.cache_data(ttl=300)` is more efficient.

### What does `@st.cache_data` do?

```python
@st.cache_data(ttl=300)    # cache for 5 minutes
def query_df(sql):
    ...  # only runs if the result isn't already cached
```

Without caching, every widget click would re-run every DB query. With caching, the first query result is stored and reused for 5 minutes — making the dashboard responsive.

### Why Plotly instead of matplotlib?

Plotly charts are interactive — users can zoom, pan, hover for details, and download as PNG. Matplotlib produces static images. For a business dashboard, interactivity is essential.

---

## How the components connect

```
┌─────────────────────────────────────────┐
│           Streamlit Dashboard           │
│   (direct MySQL queries + Plotly)       │
└──────────────────┬──────────────────────┘
                   │ Direct DB connection
┌──────────────────▼──────────────────────┐
│              MySQL Database             │
│  customers, accounts, merchants,        │
│  categories, transactions,              │
│  anomaly_scores, model_runs             │
└────┬──────────────────────┬─────────────┘
     │                      │
┌────▼────────┐    ┌────────▼──────────────┐
│ FastAPI API │    │  Anomaly Detector     │
│ (external   │    │  Isolation Forest     │
│  consumers) │    │  → anomaly_scores     │
└─────────────┘    └───────────────────────┘
```

The key flow for a new user:
1. **Setup**: Run `setup_schema.py` → creates 7 tables
2. **Data**: Run `generate_data.py` → inserts 100k+ rows
3. **Validate**: Run `validate_data.py` → checks data quality
4. **Model**: Run `anomaly_detector.py` → trains IF, writes scores to DB
5. **API**: Run `uvicorn app.main:app` → serves REST endpoints
6. **Dashboard**: Run `streamlit run dashboard/app.py` → interactive UI

---

## Common Questions

**Q: Why does the generator use `fake.unique.email()`?**
A: Email must be unique (there's a `UNIQUE KEY` on the column). `Faker.unique` guarantees no repeats within a run.

**Q: Why `SET FOREIGN_KEY_CHECKS = 0` before truncating?**
A: MySQL enforces that you can't delete a customer who has accounts. Disabling FK checks lets us truncate in any order — but we always re-enable it immediately after.

**Q: Why does the config module use `ConfigError` instead of just `ValueError`?**
A: Custom exception types let callers catch configuration errors specifically, without accidentally catching unrelated `ValueError`s from other code.

**Q: What is `pool_pre_ping=True` in the engine?**
A: MySQL disconnects idle connections after a timeout (`wait_timeout`, default 8 hours). `pool_pre_ping` sends a quick `SELECT 1` before reusing a pooled connection to check it's still alive — preventing mysterious `OperationalError: Lost connection` errors.
