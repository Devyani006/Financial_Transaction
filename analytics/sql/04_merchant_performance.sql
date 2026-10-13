WITH merchant_stats AS (
    SELECT
        m.merchant_id,
        m.merchant_name,
        m.merchant_category,
        m.country                           AS merchant_country,
        m.risk_category,
        COUNT(t.transaction_id)             AS txn_count,
        SUM(t.amount)                       AS total_volume,
        ROUND(AVG(t.amount), 2)             AS avg_txn_amount,
        COUNT(DISTINCT t.account_id)        AS unique_accounts,
        SUM(CASE WHEN t.txn_status = 'failed' THEN 1 ELSE 0 END)
                                            AS failed_txns,
        ROUND(
            100.0 * SUM(CASE WHEN t.txn_status = 'failed' THEN 1 ELSE 0 END)
            / COUNT(*), 2
        )                                   AS failure_rate_pct
    FROM merchants m
    INNER JOIN transactions t ON t.merchant_id = m.merchant_id
    GROUP BY m.merchant_id, m.merchant_name, m.merchant_category,
             m.country, m.risk_category
    HAVING COUNT(t.transaction_id) >= 10
)
SELECT
    merchant_id,
    merchant_name,
    merchant_category,
    merchant_country,
    risk_category,
    txn_count,
    ROUND(total_volume, 2)                  AS total_volume,
    avg_txn_amount,
    unique_accounts,
    failed_txns,
    failure_rate_pct,
    RANK() OVER (ORDER BY total_volume DESC)        AS volume_rank,
    ROW_NUMBER() OVER (
        PARTITION BY merchant_category
        ORDER BY total_volume DESC
    )                                               AS category_rank
FROM merchant_stats
ORDER BY total_volume DESC;
