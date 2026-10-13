import logging
import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.connection import get_db, check_connectivity
from app.api.schemas import (
    HealthResponse, KPIResponse,
    TransactionListResponse, TransactionDetail, TransactionSummary, PaginatedMeta,
    CustomerListResponse, CustomerSummary,
    MerchantListResponse, MerchantSummary,
    MonthlyTrend, AnomalyListResponse, AnomalyRecord,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Helpers

def _paginate(total: int, page: int, page_size: int) -> PaginatedMeta:
    return PaginatedMeta(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size))
    )


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


# Health

@router.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    db_health = check_connectivity()
    return HealthResponse(
        app_status="ok",
        db_status=db_health["status"],
        mysql_version=db_health.get("mysql_version"),
        timestamp=datetime.utcnow(),
    )


# KPIs

@router.get("/kpis", response_model=KPIResponse, tags=["Analytics"])
def get_kpis(db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT
            COUNT(*)                                                    AS total_transactions,
            COALESCE(SUM(amount), 0)                                    AS total_volume,
            COALESCE(ROUND(AVG(amount), 2), 0)                          AS avg_transaction_value,
            SUM(CASE WHEN txn_status = 'completed'  THEN 1 ELSE 0 END) AS completed_count,
            SUM(CASE WHEN txn_status = 'failed'     THEN 1 ELSE 0 END) AS failed_count,
            SUM(CASE WHEN txn_status = 'reversed'   THEN 1 ELSE 0 END) AS reversed_count,
            SUM(CASE WHEN txn_status = 'pending'    THEN 1 ELSE 0 END) AS pending_count,
            ROUND(100.0 * SUM(CASE WHEN txn_status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                                        AS success_rate_pct,
            ROUND(100.0 * SUM(CASE WHEN txn_status = 'failed'    THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                                        AS failure_rate_pct,
            SUM(is_anomaly)                                             AS injected_anomaly_count,
            ROUND(100.0 * SUM(is_anomaly) / COUNT(*), 2)               AS anomaly_pct,
            MIN(txn_timestamp)                                          AS earliest_txn,
            MAX(txn_timestamp)                                          AS latest_txn
        FROM transactions
    """)).fetchone()

    if not row:
        raise HTTPException(status_code=503, detail="No transaction data available")

    d = _row_to_dict(row)

    # Add model-flagged count if scores exist
    flagged_row = db.execute(text(
        "SELECT COUNT(*) FROM anomaly_scores WHERE is_flagged=1"
    )).scalar()
    d["flagged_by_model"] = int(flagged_row) if flagged_row else None

    return KPIResponse(**d)


# Transactions

@router.get("/transactions", response_model=TransactionListResponse, tags=["Transactions"])
def list_transactions(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=200, description="Rows per page"),
    status: Optional[str] = Query(default=None, description="Filter by txn_status"),
    category: Optional[str] = Query(default=None, description="Filter by category name"),
    merchant: Optional[str] = Query(default=None, description="Filter by merchant name (partial)"),
    country: Optional[str] = Query(default=None, description="Filter by transaction country"),
    date_from: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    anomaly_only: bool = Query(default=False, description="Only flagged anomalies"),
    db: Session = Depends(get_db),
):

    # Build WHERE clauses programmatically; values go into params dict
    conditions = ["1=1"]
    params = {}

    if status:
        conditions.append("t.txn_status = :status")
        params["status"] = status
    if category:
        conditions.append("cat.category_name = :category")
        params["category"] = category
    if merchant:
        conditions.append("m.merchant_name LIKE :merchant")
        params["merchant"] = f"%{merchant}%"
    if country:
        conditions.append("t.country = :country")
        params["country"] = country
    if date_from:
        conditions.append("t.txn_timestamp >= :date_from")
        params["date_from"] = date_from
    if date_to:
        conditions.append("t.txn_timestamp <= :date_to")
        params["date_to"] = date_to + " 23:59:59"
    if anomaly_only:
        conditions.append("t.is_anomaly = 1")

    where_clause = " AND ".join(conditions)

    base_sql = f"""
        FROM vw_transaction_detail t
        -- Note: the view already aliases joined columns — "t" here is the view alias
        WHERE {where_clause}
    """

    # Count total for pagination
    count_sql = f"SELECT COUNT(*) {base_sql}"
    total = db.execute(text(count_sql), params).scalar()

    # Fetch page
    offset = (page - 1) * page_size
    params["limit"]  = page_size
    params["offset"] = offset

    data_sql = f"""
        SELECT
            transaction_id, txn_timestamp, amount, currency, txn_type,
            payment_channel, txn_status, txn_country, is_anomaly,
            customer_name, customer_segment, merchant_name, category_name
        {base_sql}
        ORDER BY txn_timestamp DESC
        LIMIT :limit OFFSET :offset
    """

    rows = db.execute(text(data_sql), params).fetchall()
    items = [TransactionSummary(**_row_to_dict(r)) for r in rows]

    return TransactionListResponse(items=items, meta=_paginate(total, page, page_size))


@router.get("/transactions/{transaction_id}", response_model=TransactionDetail, tags=["Transactions"])
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Full detail for a single transaction including anomaly context."""
    row = db.execute(
        text("SELECT * FROM vw_transaction_detail WHERE transaction_id = :tid"),
        {"tid": transaction_id}
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")

    return TransactionDetail(**_row_to_dict(row))


# Customer Analytics

@router.get("/customers", response_model=CustomerListResponse, tags=["Customers"])
def list_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    segment: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Customer analytics sorted by total spend."""
    conditions = ["1=1"]
    params = {}
    if segment:
        conditions.append("segment = :segment")
        params["segment"] = segment
    if country:
        conditions.append("country = :country")
        params["country"] = country

    where = " AND ".join(conditions)
    total = db.execute(text(f"SELECT COUNT(*) FROM vw_customer_summary WHERE {where}"), params).scalar()

    offset = (page - 1) * page_size
    params["limit"]  = page_size
    params["offset"] = offset

    rows = db.execute(
        text(f"""
            SELECT * FROM vw_customer_summary
            WHERE {where}
            ORDER BY total_spent DESC
            LIMIT :limit OFFSET :offset
        """), params
    ).fetchall()

    items = [CustomerSummary(**_row_to_dict(r)) for r in rows]
    return CustomerListResponse(items=items, meta=_paginate(total, page, page_size))


# Merchant Analytics

@router.get("/merchants", response_model=MerchantListResponse, tags=["Merchants"])
def list_merchants(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    risk: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Merchant performance sorted by transaction volume."""
    conditions = ["1=1"]
    params = {}
    if category:
        conditions.append("merchant_category = :category")
        params["category"] = category
    if risk:
        conditions.append("risk_category = :risk")
        params["risk"] = risk

    where = " AND ".join(conditions)
    total = db.execute(text(f"SELECT COUNT(*) FROM vw_merchant_summary WHERE {where}"), params).scalar()

    offset = (page - 1) * page_size
    params["limit"]  = page_size
    params["offset"] = offset

    rows = db.execute(
        text(f"""
            SELECT * FROM vw_merchant_summary
            WHERE {where}
            ORDER BY total_volume DESC
            LIMIT :limit OFFSET :offset
        """), params
    ).fetchall()

    items = [MerchantSummary(**_row_to_dict(r)) for r in rows]
    return MerchantListResponse(items=items, meta=_paginate(total, page, page_size))


# Time-series Trends

@router.get("/trends/monthly", response_model=list[MonthlyTrend], tags=["Analytics"])
def monthly_trends(db: Session = Depends(get_db)):
    """Month-over-month transaction count and volume trends."""
    rows = db.execute(text("""
        WITH monthly AS (
            SELECT
                DATE_FORMAT(txn_timestamp, '%Y-%m')              AS month,
                COUNT(*)                                          AS txn_count,
                ROUND(SUM(amount), 2)                             AS total_volume,
                ROUND(AVG(amount), 2)                             AS avg_amount,
                SUM(CASE WHEN txn_status='completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN txn_status='failed'    THEN 1 ELSE 0 END) AS failed,
                SUM(is_anomaly)                                   AS anomalies
            FROM transactions
            GROUP BY DATE_FORMAT(txn_timestamp, '%Y-%m')
        ),
        with_lag AS (
            SELECT *,
                LAG(txn_count,    1) OVER (ORDER BY month) AS prev_count,
                LAG(total_volume, 1) OVER (ORDER BY month) AS prev_volume
            FROM monthly
        )
        SELECT
            month, txn_count, total_volume, avg_amount, completed, failed, anomalies,
            ROUND(100.0*(txn_count - prev_count)/NULLIF(prev_count, 0), 2)       AS count_mom_pct,
            ROUND(100.0*(total_volume - prev_volume)/NULLIF(prev_volume, 0), 2)  AS volume_mom_pct
        FROM with_lag
        ORDER BY month
    """)).fetchall()

    return [MonthlyTrend(**_row_to_dict(r)) for r in rows]


# Anomaly Monitoring

@router.get("/anomalies", response_model=AnomalyListResponse, tags=["Anomalies"])
def list_anomalies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    run_id: Optional[str] = Query(default=None, description="Filter by model_run_id"),
    db: Session = Depends(get_db),
):
    """
    Ranked list of suspicious transactions from the latest (or specified) model run.
    Results ordered by anomaly_score ascending (most anomalous first).
    """
    # Default to latest run
    if not run_id:
        latest = db.execute(text(
            "SELECT run_id FROM model_runs ORDER BY created_at DESC LIMIT 1"
        )).scalar()
        if not latest:
            return AnomalyListResponse(items=[], meta=_paginate(0, 1, page_size))
        run_id = latest

    params = {"run_id": run_id}
    total = db.execute(text(
        "SELECT COUNT(*) FROM vw_anomaly_investigation WHERE model_run_id=:run_id AND is_flagged=1"
    ), params).scalar()

    offset = (page - 1) * page_size
    params["limit"]  = page_size
    params["offset"] = offset

    rows = db.execute(text("""
        SELECT * FROM vw_anomaly_investigation
        WHERE model_run_id = :run_id AND is_flagged = 1
        ORDER BY anomaly_score ASC
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    items = [AnomalyRecord(**_row_to_dict(r)) for r in rows]
    return AnomalyListResponse(items=items, meta=_paginate(total, page, page_size))


@router.get("/anomalies/runs", tags=["Anomalies"])
def list_model_runs(db: Session = Depends(get_db)):
    """List all model training runs with their evaluation metrics."""
    rows = db.execute(text(
        "SELECT * FROM model_runs ORDER BY created_at DESC LIMIT 20"
    )).fetchall()
    return [_row_to_dict(r) for r in rows]
