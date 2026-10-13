import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.connection import engine, check_connectivity
from app.config import settings, ConfigError

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="FTI — Financial Transaction Intelligence",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] { background: #1e293b; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }

    /* KPI metric cards */
    [data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }

    /* Headers */
    h1 { color: #0f172a; font-weight: 700; }
    h2 { color: #1e293b; font-weight: 600; }
    h3 { color: #334155; }

    /* Anomaly warning banner */
    .anomaly-warning {
        background: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin: 8px 0;
    }

    /* Section dividers */
    .section-header {
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Color palette
COLORS = {
    "primary":   "#0ea5e9",
    "success":   "#10b981",
    "warning":   "#f59e0b",
    "danger":    "#ef4444",
    "neutral":   "#94a3b8",
    "dark":      "#1e293b",
    "chart":     px.colors.qualitative.Set3,
}
PLOTLY_TEMPLATE = "plotly_white"


# DB helpers

@st.cache_data(ttl=300)
def query_df(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    """
    Execute a SQL query and return a DataFrame.
    Results are cached for 5 minutes (ttl=300 seconds) to reduce DB load.
    On error, returns an empty DataFrame and shows a warning.
    """
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)
    except Exception as e:
        st.warning(f"Query error: {e}")
        return pd.DataFrame()


def get_db_status() -> dict:
    return check_connectivity()


# Navigation

def sidebar():
    with st.sidebar:
        st.markdown("## 💳 FTI Dashboard")
        st.markdown("---")

        page = st.radio(
            "Navigation",
            options=[
                "📊 Executive Overview",
                "🔍 Transaction Explorer",
                "👥 Customer Intelligence",
                "🏪 Merchant Intelligence",
                "⚠️ Anomaly Monitoring",
                "📈 SQL Insights",
            ],
            label_visibility="collapsed",
        )

        st.markdown("---")
        db_status = get_db_status()
        color = "🟢" if db_status["status"] == "ok" else "🔴"
        st.markdown(f"{color} **Database**: {db_status['status'].upper()}")
        if db_status.get("mysql_version"):
            st.caption(f"MySQL {db_status['mysql_version']}")

        st.markdown("---")
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    return page

# PAGE 1: Page Overview
def page_overview():
    st.title("📊 Executive Overview")
    st.markdown("High-level transaction KPIs and business health metrics.")

    kpi_df = query_df("""
        SELECT
            COUNT(*)                                                    AS total_transactions,
            COALESCE(SUM(amount), 0)                                    AS total_volume,
            COALESCE(ROUND(AVG(amount), 2), 0)                          AS avg_txn_value,
            SUM(CASE WHEN txn_status='completed'  THEN 1 ELSE 0 END)   AS completed,
            SUM(CASE WHEN txn_status='failed'     THEN 1 ELSE 0 END)   AS failed,
            SUM(CASE WHEN txn_status='reversed'   THEN 1 ELSE 0 END)   AS reversed,
            ROUND(100.0*SUM(CASE WHEN txn_status='completed' THEN 1 ELSE 0 END)/COUNT(*),2)
                                                                        AS success_rate,
            ROUND(100.0*SUM(CASE WHEN txn_status='failed' THEN 1 ELSE 0 END)/COUNT(*),2)
                                                                        AS failure_rate,
            SUM(is_anomaly)                                             AS injected_anomalies
        FROM transactions
    """)

    flagged_df = query_df("SELECT COUNT(*) AS n FROM anomaly_scores WHERE is_flagged=1")

    if kpi_df.empty:
        st.warning("No transaction data found. Run the data generator first.")
        return

    r = kpi_df.iloc[0]
    flagged = int(flagged_df.iloc[0]["n"]) if not flagged_df.empty else 0

    # KPI Cards
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Transactions", f"{int(r.total_transactions):,}")
    c2.metric("Total Volume", f"${float(r.total_volume):,.0f}")
    c3.metric("Avg Transaction", f"${float(r.avg_txn_value):,.2f}")
    c4.metric("Success Rate", f"{float(r.success_rate):.1f}%",
              delta=f"-{float(r.failure_rate):.1f}% failed")
    c5.metric("Flagged by Model", f"{flagged:,}",
              delta=f"{int(r.injected_anomalies):,} injected",
              delta_color="off")

    st.markdown("---")

    # Status breakdown
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Transaction Status Distribution")
        status_df = query_df("""
            SELECT txn_status, COUNT(*) AS count, ROUND(SUM(amount),2) AS volume
            FROM transactions GROUP BY txn_status ORDER BY count DESC
        """)
        if not status_df.empty:
            fig = px.pie(status_df, values="count", names="txn_status",
                         color_discrete_sequence=COLORS["chart"],
                         hole=0.4, template=PLOTLY_TEMPLATE)
            fig.update_traces(textinfo="label+percent")
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Monthly Transaction Volume")
        trend_df = query_df("""
            SELECT DATE_FORMAT(txn_timestamp,'%Y-%m') AS month,
                   COUNT(*) AS count, ROUND(SUM(amount),2) AS volume
            FROM transactions
            GROUP BY month ORDER BY month
        """)
        if not trend_df.empty:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=trend_df["month"], y=trend_df["volume"],
                                 name="Volume ($)", marker_color=COLORS["primary"],
                                 opacity=0.8), secondary_y=False)
            fig.add_trace(go.Scatter(x=trend_df["month"], y=trend_df["count"],
                                     name="Count", line=dict(color=COLORS["success"], width=2),
                                     mode="lines+markers"), secondary_y=True)
            fig.update_layout(template=PLOTLY_TEMPLATE, legend=dict(orientation="h"))
            fig.update_yaxes(title_text="Volume ($)", secondary_y=False)
            fig.update_yaxes(title_text="Count", secondary_y=True)
            st.plotly_chart(fig, use_container_width=True)

    # Payment channel breakdown
    st.subheader("Payment Channel Analysis")
    channel_df = query_df("""
        SELECT payment_channel, COUNT(*) AS count, ROUND(SUM(amount),2) AS volume,
               ROUND(AVG(amount),2) AS avg_amount
        FROM transactions GROUP BY payment_channel ORDER BY count DESC
    """)
    if not channel_df.empty:
        fig = px.bar(channel_df, x="payment_channel", y=["count", "volume"],
                     barmode="group", template=PLOTLY_TEMPLATE,
                     color_discrete_sequence=[COLORS["primary"], COLORS["success"]])
        st.plotly_chart(fig, use_container_width=True)


# PAGE 2: Transaction Explorer
def page_transactions():
    st.title("🔍 Transaction Explorer")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("Filters")

        # Status filter
        status_opts = ["All"] + ["completed", "failed", "pending", "reversed"]
        sel_status = st.selectbox("Status", status_opts)

        # Date range
        date_from = st.date_input("From", value=datetime(2023, 1, 1))
        date_to   = st.date_input("To",   value=datetime(2024, 12, 31))

        # Category filter
        cats_df = query_df("SELECT category_name FROM categories ORDER BY category_name")
        cat_opts = ["All"] + cats_df["category_name"].tolist() if not cats_df.empty else ["All"]
        sel_cat = st.selectbox("Category", cat_opts)

        # Country filter
        country_df = query_df("SELECT DISTINCT country FROM transactions ORDER BY country")
        country_opts = ["All"] + country_df["country"].tolist() if not country_df.empty else ["All"]
        sel_country = st.selectbox("Country", country_opts)

        # Anomaly filter
        anomaly_only = st.checkbox("Anomalies only")

        page_num = st.number_input("Page", min_value=1, value=1)
        page_size = st.selectbox("Per page", [25, 50, 100], index=0)

    with col2:
        # Build query
        conditions = [
            "txn_timestamp >= :date_from",
            "txn_timestamp <= :date_to"
        ]
        params = {
            "date_from": str(date_from),
            "date_to": str(date_to) + " 23:59:59",
        }
        if sel_status != "All":
            conditions.append("txn_status = :status")
            params["status"] = sel_status
        if sel_cat != "All":
            conditions.append("category_name = :category")
            params["category"] = sel_cat
        if sel_country != "All":
            conditions.append("txn_country = :country")
            params["country"] = sel_country
        if anomaly_only:
            conditions.append("is_anomaly = 1")

        where = " AND ".join(conditions)
        offset = (page_num - 1) * page_size
        params["limit"] = page_size
        params["offset"] = offset

        count_sql = f"SELECT COUNT(*) AS n FROM vw_transaction_detail WHERE {where}"
        count_df = query_df(count_sql, params)
        total = int(count_df.iloc[0]["n"]) if not count_df.empty else 0

        data_sql = f"""
            SELECT transaction_id, txn_timestamp, amount, currency, txn_type,
                   payment_channel, txn_status, txn_country, is_anomaly,
                   customer_name, merchant_name, category_name
            FROM vw_transaction_detail
            WHERE {where}
            ORDER BY txn_timestamp DESC
            LIMIT :limit OFFSET :offset
        """
        txn_df = query_df(data_sql, params)

        st.subheader(f"Results: {total:,} transactions")
        total_pages = max(1, -(-total // page_size))
        st.caption(f"Page {page_num} of {total_pages}")

        if txn_df.empty:
            st.info("No transactions match your filters.")
        else:
            # Color-code anomalies
            def highlight_anomaly(row):
                if row.get("is_anomaly", 0) == 1:
                    return ["background-color: #fef3c7"] * len(row)
                return [""] * len(row)

            st.dataframe(
                txn_df.style.apply(highlight_anomaly, axis=1),
                use_container_width=True,
                height=500,
            )



# PAGE 3: Customer Intelligence
def page_customers():
    st.title("👥 Customer Intelligence")

    # Segment distribution
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Spending by Segment")
        seg_df = query_df("""
            SELECT segment, COUNT(*) AS customer_count,
                   ROUND(SUM(total_spent),2) AS total_volume,
                   ROUND(AVG(total_spent),2) AS avg_spend
            FROM vw_customer_summary
            GROUP BY segment ORDER BY total_volume DESC
        """)
        if not seg_df.empty:
            fig = px.bar(seg_df, x="segment", y="total_volume",
                         color="segment", text="customer_count",
                         template=PLOTLY_TEMPLATE,
                         color_discrete_sequence=COLORS["chart"])
            fig.update_traces(texttemplate="%{text} customers", textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Customer Country Distribution")
        country_df = query_df("""
            SELECT country, COUNT(*) AS customers
            FROM customers
            GROUP BY country ORDER BY customers DESC LIMIT 15
        """)
        if not country_df.empty:
            fig = px.bar(country_df, x="customers", y="country",
                         orientation="h", template=PLOTLY_TEMPLATE,
                         color_discrete_sequence=[COLORS["primary"]])
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    # Top customers
    st.subheader("Top 20 Customers by Total Spend")
    top_df = query_df("""
        SELECT customer_id, full_name, segment, country,
               total_transactions, ROUND(total_spent,2) AS total_spent,
               ROUND(avg_transaction,2) AS avg_transaction,
               anomaly_count
        FROM vw_customer_summary
        ORDER BY total_spent DESC LIMIT 20
    """)
    if not top_df.empty:
        st.dataframe(top_df, use_container_width=True)

    # Cohort retention
    st.subheader("Customer Cohort Retention (First 6 Months)")
    st.info("Shows what % of customers from each signup cohort were still transacting in subsequent months.")

    cohort_df = query_df("""
        WITH cohorts AS (
            SELECT c.customer_id,
                   DATE_FORMAT(MIN(t.txn_timestamp), '%Y-%m') AS cohort_month
            FROM customers c
            INNER JOIN accounts a  ON a.customer_id = c.customer_id
            INNER JOIN transactions t ON t.account_id = a.account_id
            WHERE t.txn_status = 'completed'
            GROUP BY c.customer_id
        ),
        activity AS (
            SELECT c.customer_id,
                   DATE_FORMAT(t.txn_timestamp, '%Y-%m') AS activity_month
            FROM customers c
            INNER JOIN accounts a  ON a.customer_id = c.customer_id
            INNER JOIN transactions t ON t.account_id = a.account_id
            WHERE t.txn_status = 'completed'
            GROUP BY c.customer_id, DATE_FORMAT(t.txn_timestamp, '%Y-%m')
        ),
        combined AS (
            SELECT co.cohort_month,
                   PERIOD_DIFF(
                       REPLACE(a.activity_month,'-',''),
                       REPLACE(co.cohort_month,'-','')
                   ) AS months_later,
                   COUNT(DISTINCT co.customer_id) AS retained
            FROM cohorts co
            INNER JOIN activity a ON a.customer_id = co.customer_id
            GROUP BY co.cohort_month, months_later
        ),
        sizes AS (
            SELECT cohort_month, retained AS cohort_size
            FROM combined WHERE months_later = 0
        )
        SELECT co.cohort_month, si.cohort_size, co.months_later,
               ROUND(100.0 * co.retained / si.cohort_size, 1) AS retention_pct
        FROM combined co
        INNER JOIN sizes si ON si.cohort_month = co.cohort_month
        WHERE co.months_later BETWEEN 0 AND 6
        ORDER BY co.cohort_month, co.months_later
    """)

    if not cohort_df.empty:
        pivot = cohort_df.pivot(index="cohort_month", columns="months_later", values="retention_pct")
        fig = px.imshow(pivot, text_auto=True, aspect="auto",
                        color_continuous_scale="Blues",
                        labels=dict(x="Months After Signup", y="Cohort", color="Retention %"),
                        template=PLOTLY_TEMPLATE)
        st.plotly_chart(fig, use_container_width=True)



# PAGE 4: Merchant Intelligence
def page_merchants():
    st.title("🏪 Merchant Intelligence")

    # Top merchants
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top 15 Merchants by Volume")
        top_df = query_df("""
            SELECT merchant_name, merchant_category, risk_category,
                   txn_count, ROUND(total_volume,2) AS total_volume
            FROM vw_merchant_summary
            ORDER BY total_volume DESC LIMIT 15
        """)
        if not top_df.empty:
            fig = px.bar(top_df, x="total_volume", y="merchant_name",
                         orientation="h", color="risk_category",
                         color_discrete_map={"low": COLORS["success"],
                                             "medium": COLORS["warning"],
                                             "high": COLORS["danger"]},
                         template=PLOTLY_TEMPLATE)
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Category Performance")
        cat_df = query_df("""
            SELECT merchant_category, COUNT(*) AS merchant_count,
                   SUM(txn_count) AS total_txns,
                   ROUND(SUM(total_volume),2) AS total_volume,
                   ROUND(AVG(avg_amount),2) AS avg_amount
            FROM vw_merchant_summary
            GROUP BY merchant_category ORDER BY total_volume DESC
        """)
        if not cat_df.empty:
            fig = px.treemap(cat_df, path=["merchant_category"], values="total_volume",
                             color="avg_amount", color_continuous_scale="Blues",
                             template=PLOTLY_TEMPLATE)
            st.plotly_chart(fig, use_container_width=True)

    # Failure rates
    st.subheader("Merchants with Highest Failure Rates (≥ 50 transactions)")
    fail_df = query_df("""
        SELECT merchant_name, merchant_category, txn_count,
               failed_count, ROUND(100.0*failed_count/NULLIF(txn_count,0),2) AS failure_rate_pct
        FROM vw_merchant_summary
        WHERE txn_count >= 50
        ORDER BY failure_rate_pct DESC LIMIT 15
    """)
    if not fail_df.empty:
        fig = px.bar(fail_df, x="merchant_name", y="failure_rate_pct",
                     color="failure_rate_pct", color_continuous_scale="Reds",
                     template=PLOTLY_TEMPLATE)
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    # Full merchant table
    st.subheader("All Merchants")
    all_df = query_df("SELECT * FROM vw_merchant_summary ORDER BY total_volume DESC")
    if not all_df.empty:
        st.dataframe(all_df, use_container_width=True)


# PAGE 5: Anomaly Monitoring
def page_anomalies():
    st.title("⚠️ Anomaly Monitoring")

    st.markdown("""
    <div class="anomaly-warning">
    ⚠️ <strong>Important:</strong> Transactions flagged here show <em>unusual patterns</em>
    detected by a machine learning model. A flag is NOT proof of fraud or wrongdoing.
    All flagged transactions require human review before any action is taken.
    </div>
    """, unsafe_allow_html=True)
    st.markdown("")

    # Check if model has been run
    runs_df = query_df("SELECT * FROM model_runs ORDER BY created_at DESC LIMIT 10")

    if runs_df.empty:
        st.info(
            "No anomaly detection runs found.\n\n"
            "Run the model first:\n```\npython analytics/models/anomaly_detector.py\n```"
        )
        return

    # Model run selector
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_run = st.selectbox(
            "Select Model Run",
            options=runs_df["run_id"].tolist(),
            format_func=lambda x: f"{x} — F1: {runs_df[runs_df['run_id']==x]['f1_score'].values[0]:.3f}"
            if runs_df[runs_df['run_id']==x]['f1_score'].notna().any() else x
        )

    with col2:
        run_info = runs_df[runs_df["run_id"] == selected_run].iloc[0]
        st.metric("Flagged Transactions", f"{int(run_info['n_flagged']):,}")
        if run_info.get("f1_score"):
            st.metric("Model F1 Score", f"{run_info['f1_score']:.3f}")

    # Model performance metrics
    st.subheader("Model Evaluation")
    mcol1, mcol2, mcol3 = st.columns(3)
    if run_info.get("precision_score"):
        mcol1.metric("Precision", f"{run_info['precision_score']:.3f}",
                     help="Of all flagged transactions, what fraction are actual anomalies?")
        mcol2.metric("Recall", f"{run_info['recall_score']:.3f}",
                     help="Of all actual anomalies, what fraction did we catch?")
        mcol3.metric("F1 Score", f"{run_info['f1_score']:.3f}",
                     help="Harmonic mean of precision and recall")
    else:
        st.caption("Evaluation metrics not available for this run.")

    st.markdown("---")

    # Flagged transactions
    st.subheader(f"Top Suspicious Transactions (Run: {selected_run})")

    flagged_df = query_df("""
        SELECT transaction_id, txn_timestamp, amount, currency,
               txn_type, txn_status, txn_country,
               ROUND(anomaly_score, 4) AS anomaly_score,
               ground_truth_label, ground_truth_type,
               customer_name, segment, merchant_name,
               merchant_category, risk_category, category_name
        FROM vw_anomaly_investigation
        WHERE model_run_id = :run_id AND is_flagged = 1
        ORDER BY anomaly_score ASC
        LIMIT 100
    """, {"run_id": selected_run})

    if flagged_df.empty:
        st.info("No flagged transactions for this run.")
    else:
        # Score distribution
        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.histogram(flagged_df, x="anomaly_score", nbins=30,
                               title="Anomaly Score Distribution (flagged only)",
                               template=PLOTLY_TEMPLATE,
                               color_discrete_sequence=[COLORS["warning"]])
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            # Amount vs score scatter
            fig = px.scatter(flagged_df, x="amount", y="anomaly_score",
                             color="risk_category",
                             color_discrete_map={"low": COLORS["success"],
                                                 "medium": COLORS["warning"],
                                                 "high": COLORS["danger"]},
                             hover_data=["customer_name", "merchant_name"],
                             title="Amount vs Anomaly Score",
                             template=PLOTLY_TEMPLATE)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            flagged_df,
            use_container_width=True,
            height=400,
            column_config={
                "anomaly_score": st.column_config.NumberColumn(format="%.4f"),
                "amount": st.column_config.NumberColumn(format="$%.2f"),
            }
        )

    # Injected anomaly breakdown
    st.subheader("Injected Anomaly Types (Ground Truth)")
    atype_df = query_df("""
        SELECT anomaly_type, COUNT(*) AS count
        FROM transactions WHERE is_anomaly = 1
        GROUP BY anomaly_type ORDER BY count DESC
    """)
    if not atype_df.empty:
        fig = px.bar(atype_df, x="anomaly_type", y="count",
                     color="anomaly_type", template=PLOTLY_TEMPLATE,
                     color_discrete_sequence=COLORS["chart"])
        st.plotly_chart(fig, use_container_width=True)



# PAGE 6: SQL Insights
def page_sql_insights():
    st.title("📈 SQL Insights")
    st.markdown("Business insights derived from SQL analytics queries.")

    tab1, tab2, tab3 = st.tabs(["Transaction Velocity", "Spending Patterns", "Data Quality"])

    with tab1:
        st.subheader("High-Velocity Accounts (3+ transactions in one hour)")
        vel_df = query_df("""
            WITH hourly AS (
                SELECT account_id,
                       DATE_FORMAT(txn_timestamp, '%Y-%m-%d %H:00:00') AS txn_hour,
                       COUNT(*) AS txn_count,
                       ROUND(SUM(amount), 2) AS hour_volume
                FROM transactions
                GROUP BY account_id, txn_hour
                HAVING COUNT(*) >= 3
            )
            SELECT h.account_id, c.full_name, c.segment,
                   h.txn_hour, h.txn_count, h.hour_volume
            FROM hourly h
            INNER JOIN accounts a ON a.account_id = h.account_id
            INNER JOIN customers c ON c.customer_id = a.customer_id
            ORDER BY h.txn_count DESC
            LIMIT 30
        """)
        if not vel_df.empty:
            fig = px.scatter(vel_df, x="txn_hour", y="txn_count",
                             size="hour_volume", color="segment",
                             hover_data=["full_name", "account_id"],
                             title="Transaction Bursts by Account",
                             template=PLOTLY_TEMPLATE)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(vel_df, use_container_width=True)

    with tab2:
        st.subheader("Spending by Hour of Day")
        hour_df = query_df("""
            SELECT HOUR(txn_timestamp) AS hour_of_day,
                   COUNT(*) AS txn_count,
                   ROUND(AVG(amount), 2) AS avg_amount,
                   ROUND(SUM(amount), 2) AS total_volume
            FROM transactions WHERE txn_status = 'completed'
            GROUP BY HOUR(txn_timestamp) ORDER BY hour_of_day
        """)
        if not hour_df.empty:
            fig = make_subplots(rows=1, cols=2,
                                subplot_titles=["Transaction Count by Hour",
                                                "Average Amount by Hour"])
            fig.add_trace(go.Bar(x=hour_df["hour_of_day"], y=hour_df["txn_count"],
                                 marker_color=COLORS["primary"], name="Count"), row=1, col=1)
            fig.add_trace(go.Scatter(x=hour_df["hour_of_day"], y=hour_df["avg_amount"],
                                     mode="lines+markers", line=dict(color=COLORS["success"]),
                                     name="Avg Amount"), row=1, col=2)
            fig.update_layout(template=PLOTLY_TEMPLATE, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Transaction Type Mix by Customer Segment")
        type_df = query_df("""
            SELECT c.segment, t.txn_type, COUNT(*) AS count
            FROM transactions t
            INNER JOIN accounts a ON a.account_id = t.account_id
            INNER JOIN customers c ON c.customer_id = a.customer_id
            GROUP BY c.segment, t.txn_type
        """)
        if not type_df.empty:
            fig = px.bar(type_df, x="segment", y="count", color="txn_type",
                         barmode="stack", template=PLOTLY_TEMPLATE,
                         color_discrete_sequence=COLORS["chart"])
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Data Quality Summary")
        quality_checks = [
            ("Negative amounts",    "SELECT COUNT(*) FROM transactions WHERE amount <= 0"),
            ("Future timestamps",   "SELECT COUNT(*) FROM transactions WHERE txn_timestamp > NOW()"),
            ("Invalid currency",    "SELECT COUNT(*) FROM transactions WHERE currency NOT REGEXP '^[A-Z]{3}$'"),
            ("Orphaned accounts",   "SELECT COUNT(*) FROM accounts a LEFT JOIN customers c ON c.customer_id=a.customer_id WHERE c.customer_id IS NULL"),
            ("Unlabeled anomalies", "SELECT COUNT(*) FROM transactions WHERE is_anomaly=1 AND anomaly_type IS NULL"),
        ]
        results = []
        with engine.connect() as conn:
            for name, sql in quality_checks:
                try:
                    n = conn.execute(text(sql)).scalar()
                    results.append({"Check": name, "Issues": n,
                                    "Status": "✅ PASS" if n == 0 else "❌ FAIL"})
                except Exception as e:
                    results.append({"Check": name, "Issues": "ERR", "Status": "⚠️ ERR"})

        qdf = pd.DataFrame(results)
        st.dataframe(qdf, use_container_width=True, hide_index=True)



# Main
def main():
    try:
        # Validate config before rendering any page
        _ = settings.db
    except ConfigError as e:
        st.error(f"**Configuration Error**: {e}")
        st.info("Copy `.env.example` to `.env` and fill in your database password.")
        st.stop()

    page = sidebar()

    if   "Overview"     in page: page_overview()
    elif "Transaction"  in page: page_transactions()
    elif "Customer"     in page: page_customers()
    elif "Merchant"     in page: page_merchants()
    elif "Anomaly"      in page: page_anomalies()
    elif "SQL"          in page: page_sql_insights()


if __name__ == "__main__":
    main()
