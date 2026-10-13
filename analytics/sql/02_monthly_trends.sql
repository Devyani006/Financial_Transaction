WITH monthly AS (
    SELECT
        DATE_FORMAT(txn_timestamp, '%Y-%m')             AS month,
        COUNT(*)                                         AS txn_count,
        SUM(amount)                                      AS total_volume,
        ROUND(AVG(amount), 2)                            AS avg_amount,
        SUM(CASE WHEN txn_status = 'completed' THEN 1 ELSE 0 END) AS completed,
        SUM(CASE WHEN txn_status = 'failed'    THEN 1 ELSE 0 END) AS failed,
        SUM(is_anomaly)                                  AS anomalies
    FROM transactions
    GROUP BY DATE_FORMAT(txn_timestamp, '%Y-%m')
),
with_lag AS (
    SELECT
        month,
        txn_count,
        total_volume,
        avg_amount,
        completed,
        failed,
        anomalies,
        LAG(txn_count,    1) OVER (ORDER BY month)  AS prev_month_count,
        LAG(total_volume, 1) OVER (ORDER BY month)  AS prev_month_volume
    FROM monthly
)
SELECT
    month,
    txn_count,
    ROUND(total_volume, 2)                               AS total_volume,
    avg_amount,
    completed,
    failed,
    anomalies,
    ROUND(100.0 * (txn_count - prev_month_count) / NULLIF(prev_month_count, 0), 2)
                                                         AS count_mom_pct,
    ROUND(100.0 * (total_volume - prev_month_volume) / NULLIF(prev_month_volume, 0), 2)
                                                         AS volume_mom_pct
FROM with_lag
ORDER BY month;
