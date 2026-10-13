from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# Shared

class PaginatedMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


# Health

class HealthResponse(BaseModel):
    app_status: str
    db_status: str
    mysql_version: Optional[str] = None
    timestamp: datetime


# KPIs

class KPIResponse(BaseModel):
    total_transactions: int
    total_volume: float
    avg_transaction_value: float
    completed_count: int
    failed_count: int
    reversed_count: int
    pending_count: int
    success_rate_pct: float
    failure_rate_pct: float
    injected_anomaly_count: int
    anomaly_pct: float
    earliest_txn: Optional[datetime]
    latest_txn: Optional[datetime]
    flagged_by_model: Optional[int] = None


# Transactions

class TransactionSummary(BaseModel):
    transaction_id: int
    txn_timestamp: datetime
    amount: float
    currency: str
    txn_type: str
    payment_channel: str
    txn_status: str
    txn_country: str
    is_anomaly: int
    customer_name: str
    customer_segment: str
    merchant_name: str
    category_name: str


class TransactionDetail(TransactionSummary):
    account_id: int
    account_type: str
    customer_id: int
    customer_country: str
    merchant_id: int
    merchant_category: str
    merchant_risk: str
    anomaly_type: Optional[str] = None
    category_description: str


class TransactionListResponse(BaseModel):
    items: list[TransactionSummary]
    meta: PaginatedMeta


# Customer Analytics

class CustomerSummary(BaseModel):
    customer_id: int
    full_name: str
    segment: str
    country: str
    signup_date: Optional[datetime]
    account_count: int
    total_transactions: int
    total_spent: float
    avg_transaction: float
    last_transaction_at: Optional[datetime]
    anomaly_count: int


class CustomerListResponse(BaseModel):
    items: list[CustomerSummary]
    meta: PaginatedMeta


# Merchant Analytics

class MerchantSummary(BaseModel):
    merchant_id: int
    merchant_name: str
    merchant_category: str
    merchant_country: str
    risk_category: str
    txn_count: int
    total_volume: float
    avg_amount: float
    unique_accounts: int
    failed_count: int
    reversed_count: int
    anomaly_count: int


class MerchantListResponse(BaseModel):
    items: list[MerchantSummary]
    meta: PaginatedMeta


# Time-series Trends

class MonthlyTrend(BaseModel):
    month: str
    txn_count: int
    total_volume: float
    avg_amount: float
    completed: int
    failed: int
    anomalies: int
    count_mom_pct: Optional[float] = None
    volume_mom_pct: Optional[float] = None


# Anomaly Monitoring

class AnomalyRecord(BaseModel):
    score_id: int
    transaction_id: int
    model_run_id: str
    anomaly_score: float
    is_flagged: int
    scored_at: datetime
    txn_timestamp: datetime
    amount: float
    currency: str
    txn_type: str
    txn_status: str
    txn_country: str
    ground_truth_label: int
    customer_name: str
    segment: str
    merchant_name: str
    merchant_category: str
    risk_category: str
    category_name: str


class AnomalyListResponse(BaseModel):
    items: list[AnomalyRecord]
    meta: PaginatedMeta
    disclaimer: str = (
        "⚠ Flagged transactions indicate suspicious patterns only. "
        "They are NOT confirmed fraud. Manual investigation is required."
    )
