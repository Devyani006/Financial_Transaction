WITH customer_totals AS (
    SELECT
        c.customer_id,
        c.full_name,
        c.segment,
        c.country,
        COUNT(t.transaction_id)          AS txn_count,
        SUM(t.amount)                    AS total_spent,
        ROUND(AVG(t.amount), 2)          AS avg_spend,
        MAX(t.amount)                    AS max_single_txn,
        MAX(t.txn_timestamp)             AS last_transaction_date
    FROM customers c
    INNER JOIN accounts a  ON a.customer_id = c.customer_id
    INNER JOIN transactions t ON t.account_id = a.account_id
    WHERE t.txn_status = 'completed'
    GROUP BY c.customer_id, c.full_name, c.segment, c.country
    HAVING COUNT(t.transaction_id) >= 5
)
SELECT
    customer_id,
    full_name,
    segment,
    country,
    txn_count,
    ROUND(total_spent, 2)               AS total_spent,
    avg_spend,
    max_single_txn,
    last_transaction_date,
    RANK() OVER (ORDER BY total_spent DESC)          AS spend_rank,
    RANK() OVER (PARTITION BY segment ORDER BY total_spent DESC) AS segment_rank,
    ROUND(
        100.0 * PERCENT_RANK() OVER (ORDER BY total_spent),
    1)                                               AS spend_percentile
FROM customer_totals
ORDER BY total_spent DESC
LIMIT 100;
