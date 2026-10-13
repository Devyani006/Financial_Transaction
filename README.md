# Financial Transaction Intelligence (FTI)

> **SQL-first fintech analytics platform** — MySQL · Python · FastAPI · Streamlit · Isolation Forest

A portfolio-quality, locally runnable analytics application that demonstrates real financial data engineering: normalized database design, advanced SQL analytics, machine learning anomaly detection, a REST API, and an interactive business intelligence dashboard.

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Features & Architecture](#features--architecture)
3. [Technology Stack](#technology-stack)
4. [Repository Structure](#repository-structure)
5. [ER Diagram](#er-diagram)
6. [Windows PowerShell Setup](#windows-powershell-setup)
7. [Running the Application](#running-the-application)
8. [Running Tests](#running-tests)
9. [Sample SQL Queries](#sample-sql-queries)
10. [Limitations & Future Work](#limitations--future-work)

---

## Project Overview

FTI simulates the analytics infrastructure of a fintech company:

- A **normalized MySQL database** storing customers, accounts, merchants, and transactions
- **100,000+ synthetic transactions** with realistic distributions and injected anomalies
- **Advanced SQL analytics** covering window functions, CTEs, cohort analysis, and data quality checks
- **Isolation Forest** anomaly detection with chronological evaluation and no label leakage
- A **FastAPI REST API** with OpenAPI documentation
- A **Streamlit dashboard** with 6 interactive sections powered by live database queries

> **Disclaimer:** All data is synthetically generated. No real customer data is used. Anomaly flags indicate suspicious patterns for investigation — not confirmed fraud.

---

## Features & Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Streamlit Dashboard (dashboard/app.py)                         │
│  6 sections: Overview · Explorer · Customers ·                  │
│              Merchants · Anomalies · SQL Insights                │
└───────────────────────┬──────────────────────────────────────────┘
                        │ Direct DB queries (cached)
         ┌──────────────▼──────────────────────────┐
         │         MySQL 8.0 Database              │
         │  financial_transaction                  │
         │  7 tables, 4 views, optimized indexes   │
         └──┬──────────────────┬───────────────────┘
            │                  │
   ┌────────▼──────┐  ┌────────▼──────────────────┐
   │  FastAPI API  │  │  Anomaly Detection        │
   │  app/main.py  │  │  analytics/models/        │
   │  /api/v1/...  │  │  Isolation Forest         │
   └───────────────┘  └───────────────────────────┘
```

---

## Technology Stack

| Component | Technology | Reason |
|---|---|---|
| Database | MySQL 8.0 | Production-grade RDBMS with window functions |
| ORM / Driver | SQLAlchemy + PyMySQL | Connection pooling, parameterized queries |
| Data Processing | pandas + NumPy | Fast DataFrame operations |
| API | FastAPI | Type-safe, auto-documented REST API |
| Dashboard | Streamlit | Rapid interactive analytics UI |
| Visualizations | Plotly | Interactive charts with zoom/hover |
| Anomaly Detection | scikit-learn IsolationForest | Unsupervised, no labeled training data required |
| Configuration | python-dotenv | Keeps secrets out of source code |
| Synthetic Data | Faker | Realistic names, emails, dates |
| Testing | pytest | Unit + integration test separation |

---

## Repository Structure

```
Financial_Transaction/
├── .env.example              ← Copy to .env and add password
├── .gitignore
├── requirements.txt
├── pytest.ini
├── README.md
│
├── app/                      ← Backend application
│   ├── config.py             ← Environment variable loading & validation
│   ├── main.py               ← FastAPI app entry point
│   ├── api/
│   │   ├── routes.py         ← All API endpoints
│   │   └── schemas.py        ← Pydantic request/response models
│   └── db/
│       └── connection.py     ← Engine, session factory, health check
│
├── analytics/
│   ├── sql/                  ← SQL analytics queries
│   │   ├── 01_kpi_overview.sql
│   │   ├── 02_monthly_trends.sql
│   │   ├── 03_customer_spending_rank.sql
│   │   ├── 04_merchant_performance.sql
│   │   ├── 05_cohort_retention.sql
│   │   ├── 06_transaction_velocity.sql
│   │   ├── 07_category_analysis.sql
│   │   ├── 08_data_quality_checks.sql
│   │   └── 09_views.sql
│   └── models/
│       └── anomaly_detector.py ← Isolation Forest pipeline
│
├── dashboard/
│   └── app.py                ← Streamlit dashboard (6 sections)
│
├── scripts/
│   ├── setup_schema.py       ← Create database tables (idempotent)
│   ├── generate_data.py      ← Generate synthetic data
│   └── validate_data.py      ← Run data quality checks
│
├── sql/
│   └── schema.sql            ← Complete DDL (7 tables + indexes)
│
├── tests/
│   ├── conftest.py           ← Shared fixtures
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_data_generation.py
│   │   └── test_anomaly_model.py
│   └── integration/
│       └── test_api.py       ← Requires MySQL + .env
│
├── docs/
│   ├── ER_DIAGRAM.md
│   └── LEARNING_GUIDE.md
│
└── models/
    └── artifacts/            ← Saved model files (git-ignored)
```

---

## ER Diagram

See [`docs/ER_DIAGRAM.md`](docs/ER_DIAGRAM.md) for the full ASCII diagram and relationship explanations.

```
customers (1) ──── (many) accounts (1) ──── (many) transactions
                                                  │              │
                              merchants (1) ───────┘    categories (1) ────┘
                                        transactions ──── anomaly_scores
```

---

## Windows PowerShell Setup

### Prerequisites

- Python 3.10+ (tested on 3.13.9)
- MySQL 8.0 running locally
- `financial_transaction` database and `fti_app` user already created

### Step 1 — Clone and enter directory

```powershell
cd d:\Financial_Transaction
```

### Step 2 — Create virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> If you get an execution policy error:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Step 3 — Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 4 — Configure environment

```powershell
Copy-Item .env.example .env
notepad .env   # Replace 'replace_with_your_local_password' with your fti_app password
```

### Step 5 — Initialize database schema

```powershell
python scripts/setup_schema.py
```

Expected output: all 7 tables shown with ✓

### Step 6 — Generate synthetic data

```powershell
# First run (safe)
python scripts/generate_data.py

# View current counts
python scripts/generate_data.py --counts

# Reset and regenerate (deletes all data!)
python scripts/generate_data.py --reset
```

> ⚠️ `--reset` deletes all data. The script warns you before doing so.

### Step 7 — Validate data quality

```powershell
python scripts/validate_data.py
python scripts/validate_data.py --output data/reports/quality_report.txt
```

### Step 8 — Create SQL views

```powershell
# Run this in MySQL Workbench or:
mysql -u fti_app -p financial_transaction < analytics/sql/09_views.sql
```

### Step 9 — Run anomaly detection

```powershell
python analytics/models/anomaly_detector.py
python analytics/models/anomaly_detector.py --contamination 0.03 --seed 123
```

---

## Running the Application

### Start the FastAPI backend

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

API documentation: http://127.0.0.1:8000/docs
Health check: http://127.0.0.1:8000/api/v1/health

### Start the Streamlit dashboard

```powershell
# In a second terminal (with venv activated)
streamlit run dashboard/app.py
```

Dashboard: http://localhost:8501

---

## Running Tests

### Unit tests only (no MySQL required)

```powershell
pytest tests/unit/ -v
```

### All tests (MySQL + .env required for integration)

```powershell
pytest -v
```

### Run a specific test class

```powershell
pytest tests/unit/test_anomaly_model.py::TestFeatureColumns -v
```

### Test coverage report

```powershell
pip install pytest-cov
pytest tests/unit/ --cov=app --cov=analytics --cov-report=html
```

> **Note:** Integration tests in `tests/integration/` are automatically **skipped** if MySQL is unavailable. They will never accidentally modify the `financial_transaction` database — they target `financial_transaction_test`.

---

## Sample SQL Queries

### 1. Top customers by total spend

```sql
SELECT c.full_name, c.segment,
       COUNT(t.transaction_id) AS txn_count,
       ROUND(SUM(t.amount), 2) AS total_spent,
       RANK() OVER (ORDER BY SUM(t.amount) DESC) AS rank
FROM customers c
INNER JOIN accounts a  ON a.customer_id = c.customer_id
INNER JOIN transactions t ON t.account_id = a.account_id
WHERE t.txn_status = 'completed'
GROUP BY c.customer_id, c.full_name, c.segment
ORDER BY total_spent DESC
LIMIT 10;
```

**Technique:** Multi-table JOIN, GROUP BY, RANK() window function
**Output:** Top 10 customers ranked by lifetime value

### 2. Month-over-month growth

```sql
WITH monthly AS (
    SELECT DATE_FORMAT(txn_timestamp,'%Y-%m') AS month,
           COUNT(*) AS cnt, ROUND(SUM(amount),2) AS vol
    FROM transactions GROUP BY month
)
SELECT month, cnt, vol,
       ROUND(100*(cnt - LAG(cnt) OVER (ORDER BY month))
             / NULLIF(LAG(cnt) OVER (ORDER BY month), 0), 2) AS mom_pct
FROM monthly ORDER BY month;
```

**Technique:** CTE + LAG() window function
**Output:** Month-over-month transaction growth percentage

### 3. Find velocity bursts (fraud indicator)

```sql
SELECT account_id,
       DATE_FORMAT(txn_timestamp,'%Y-%m-%d %H:00:00') AS hour,
       COUNT(*) AS count_in_hour
FROM transactions
GROUP BY account_id, hour
HAVING count_in_hour >= 5
ORDER BY count_in_hour DESC;
```

**Technique:** GROUP BY + HAVING
**Output:** Accounts with 5+ transactions in a single hour

---

## Screenshots

> Add screenshots here after running the dashboard. Suggested captures:
> - Executive Overview KPI cards
> - Transaction Explorer with filters applied
> - Cohort retention heatmap
> - Anomaly monitoring scatter plot

---

## Limitations & Assumptions

- **Synthetic data only:** No real financial data. Patterns are statistically plausible, not industry-calibrated.
- **No authentication:** The API has no auth layer — suitable for local development only.
- **Single-node MySQL:** No replication or clustering. Not production-ready.
- **Isolation Forest limitations:** Unsupervised model — performance depends on anomaly contamination estimate. May miss novel fraud patterns.
- **No real-time streaming:** Data is batch-generated. A production system would use Kafka or similar.
- **Local only:** No cloud deployment. No Docker configuration provided.

## Future Improvements

- [ ] Add JWT authentication to the FastAPI backend
- [ ] Implement a Kafka consumer for real-time transaction streaming
- [ ] Add SHAP values to explain individual anomaly predictions
- [ ] Build a model retraining scheduler
- [ ] Add Alembic for database migration management
- [ ] Dockerize the entire stack with docker-compose
- [ ] Add a network graph visualization for transaction relationships

---

## License

MIT License. Built for educational and portfolio purposes.
