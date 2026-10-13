WITH category_totals AS (
    SELECT
        ca.category_id,
        ca.category_name,
        COUNT(t.transaction_id)                   AS txn_count,
        SUM(t.amount)                             AS total_volume,
        ROUND(AVG(t.amount), 2)                   AS avg_amount,
        MAX(t.amount)                             AS max_amount,
        COUNT(DISTINCT t.account_id)              AS unique_accounts,
        SUM(t.is_anomaly)                         AS anomaly_count
    FROM categories ca
    LEFT JOIN transactions t ON t.category_id = ca.category_id
    GROUP BY ca.category_id, ca.category_name
),
with_share AS (
    SELECT
        *,
        SUM(total_volume) OVER ()                 AS grand_total,
        SUM(txn_count)    OVER ()                 AS grand_count
    FROM category_totals
)
SELECT
    category_id,
    category_name,
    txn_count,
    ROUND(total_volume, 2)                        AS total_volume,
    avg_amount,
    max_amount,
    unique_accounts,
    anomaly_count,
    ROUND(100.0 * total_volume / NULLIF(grand_total, 0), 2) AS volume_share_pct,
    ROUND(100.0 * txn_count   / NULLIF(grand_count, 0), 2)  AS count_share_pct,
    CASE
        WHEN txn_count > 0
         AND CAST(anomaly_count AS DECIMAL) / txn_count > 0.05 THEN 'high'
        WHEN txn_count > 0
         AND CAST(anomaly_count AS DECIMAL) / txn_count > 0.02 THEN 'medium'
        ELSE 'low'
    END                                           AS anomaly_risk_level,
    RANK() OVER (ORDER BY total_volume DESC)      AS volume_rank
FROM with_share
ORDER BY total_volume DESC;
