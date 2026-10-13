WITH cohorts AS (
    SELECT
        c.customer_id,
        DATE_FORMAT(MIN(t.txn_timestamp), '%Y-%m') AS cohort_month
    FROM customers c
    INNER JOIN accounts a  ON a.customer_id = c.customer_id
    INNER JOIN transactions t ON t.account_id = a.account_id
    WHERE t.txn_status = 'completed'
    GROUP BY c.customer_id
),
activity AS (
    SELECT
        c.customer_id,
        DATE_FORMAT(t.txn_timestamp, '%Y-%m') AS activity_month
    FROM customers c
    INNER JOIN accounts a  ON a.customer_id = c.customer_id
    INNER JOIN transactions t ON t.account_id = a.account_id
    WHERE t.txn_status = 'completed'
    GROUP BY c.customer_id, DATE_FORMAT(t.txn_timestamp, '%Y-%m')
),
cohort_activity AS (
    SELECT
        co.cohort_month,
        PERIOD_DIFF(
            REPLACE(a.activity_month, '-', ''),
            REPLACE(co.cohort_month,  '-', '')
        )                                    AS months_since_cohort,
        COUNT(DISTINCT co.customer_id)       AS retained_customers
    FROM cohorts co
    INNER JOIN activity a ON a.customer_id = co.customer_id
    GROUP BY co.cohort_month, months_since_cohort
),
cohort_sizes AS (
    SELECT cohort_month, retained_customers AS cohort_size
    FROM cohort_activity
    WHERE months_since_cohort = 0
)
SELECT
    ca.cohort_month,
    cs.cohort_size,
    ca.months_since_cohort,
    ca.retained_customers,
    ROUND(100.0 * ca.retained_customers / cs.cohort_size, 1) AS retention_rate_pct
FROM cohort_activity ca
INNER JOIN cohort_sizes cs ON cs.cohort_month = ca.cohort_month
WHERE ca.months_since_cohort BETWEEN 0 AND 12
ORDER BY ca.cohort_month, ca.months_since_cohort;
