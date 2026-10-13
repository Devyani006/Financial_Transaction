WITH account_hourly AS (
    SELECT
        account_id,
        DATE_FORMAT(txn_timestamp, '%Y-%m-%d %H:00:00') AS txn_hour,
        COUNT(*)                                         AS txns_in_hour,
        SUM(amount)                                      AS volume_in_hour,
        GROUP_CONCAT(
            DISTINCT txn_status ORDER BY txn_status
            SEPARATOR ', '
        )                                                AS statuses
    FROM transactions
    GROUP BY account_id, DATE_FORMAT(txn_timestamp, '%Y-%m-%d %H:00:00')
    HAVING COUNT(*) >= 3
),
ranked AS (
    SELECT
        ah.*,
        a.customer_id,
        c.full_name,
        c.segment,
        RANK() OVER (ORDER BY ah.txns_in_hour DESC) AS velocity_rank
    FROM account_hourly ah
    INNER JOIN accounts a  ON a.account_id  = ah.account_id
    INNER JOIN customers c ON c.customer_id = a.customer_id
)
SELECT
    velocity_rank,
    account_id,
    customer_id,
    full_name,
    segment,
    txn_hour,
    txns_in_hour,
    ROUND(volume_in_hour, 2) AS volume_in_hour,
    statuses
FROM ranked
ORDER BY velocity_rank
LIMIT 50;
