SELECT
    COUNT(*)                                                    AS total_transactions,
    SUM(amount)                                                 AS total_volume,
    ROUND(AVG(amount), 2)                                       AS avg_transaction_value,
    ROUND(MEDIAN(amount), 2)                                    AS median_transaction_value,


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
FROM transactions;
