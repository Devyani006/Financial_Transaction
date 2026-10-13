SELECT 'customers'     AS tbl, COUNT(*) AS row_count FROM customers
UNION ALL
SELECT 'accounts',              COUNT(*) FROM accounts
UNION ALL
SELECT 'merchants',             COUNT(*) FROM merchants
UNION ALL
SELECT 'categories',            COUNT(*) FROM categories
UNION ALL
SELECT 'transactions',          COUNT(*) FROM transactions
UNION ALL
SELECT 'anomaly_scores',        COUNT(*) FROM anomaly_scores
UNION ALL
SELECT 'model_runs',            COUNT(*) FROM model_runs;

-- 2. Orphaned accounts (no matching customer)
SELECT 'orphaned_accounts' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM accounts a
LEFT JOIN customers c ON c.customer_id = a.customer_id
WHERE c.customer_id IS NULL;

-- 3. Transactions with non-existent account, merchant, or category
SELECT 'orphaned_txn_account' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions t
LEFT JOIN accounts a ON a.account_id = t.account_id
WHERE a.account_id IS NULL;

SELECT 'orphaned_txn_merchant' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions t
LEFT JOIN merchants m ON m.merchant_id = t.merchant_id
WHERE m.merchant_id IS NULL;

-- 4. Negative or zero amounts (should not exist for purchases)
SELECT 'negative_amounts' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions
WHERE amount <= 0;

-- 5. Future timestamps
SELECT 'future_timestamps' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions
WHERE txn_timestamp > NOW();

-- 6. Invalid currency codes (should be 3-letter ISO)
SELECT 'invalid_currency' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions
WHERE currency NOT REGEXP '^[A-Z]{3}$';

-- 7. Duplicate transaction IDs (should never happen with AUTO_INCREMENT)
SELECT 'duplicate_txn_ids' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    SELECT transaction_id, COUNT(*) AS cnt
    FROM transactions
    GROUP BY transaction_id
    HAVING cnt > 1
) duplicates;

-- 8. Anomaly label consistency: is_anomaly=1 must have anomaly_type set
SELECT 'anomaly_type_missing' AS check_name,
       COUNT(*) AS issue_count,
       CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM transactions
WHERE is_anomaly = 1 AND (anomaly_type IS NULL OR anomaly_type = '');

-- 9. Customers without any account
SELECT 'customers_without_account' AS check_name,
       COUNT(*) AS issue_count,
       'WARNING' AS status        -- not a hard failure, but noteworthy
FROM customers c
LEFT JOIN accounts a ON a.customer_id = c.customer_id
WHERE a.account_id IS NULL;

-- 10. Amount distribution sanity check
SELECT
    'amount_stats'       AS check_name,
    MIN(amount)          AS min_amount,
    MAX(amount)          AS max_amount,
    ROUND(AVG(amount),2) AS mean_amount,
    COUNT(*)             AS total_rows
FROM transactions;
