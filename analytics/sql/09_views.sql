USE financial_transaction;
CREATE OR REPLACE VIEW vw_transaction_detail AS
SELECT
    t.transaction_id,
    t.txn_timestamp,
    t.amount,
    t.currency,
    t.txn_type,
    t.payment_channel,
    t.txn_status,
    t.country                AS txn_country,
    t.is_anomaly,
    t.anomaly_type,
    a.account_id,
    a.account_type,
    c.customer_id,
    c.full_name              AS customer_name,
    c.segment                AS customer_segment,
    c.country                AS customer_country,
    m.merchant_id,
    m.merchant_name,
    m.merchant_category,
    m.risk_category          AS merchant_risk,
    cat.category_name,
    cat.description          AS category_description
FROM transactions t
INNER JOIN accounts a   ON a.account_id   = t.account_id
INNER JOIN customers c  ON c.customer_id  = a.customer_id
INNER JOIN merchants m  ON m.merchant_id  = t.merchant_id
INNER JOIN categories cat ON cat.category_id = t.category_id;


CREATE OR REPLACE VIEW vw_customer_summary AS
SELECT
    c.customer_id,
    c.full_name,
    c.segment,
    c.country,
    c.signup_date,
    c.account_status,
    COUNT(DISTINCT a.account_id)        AS account_count,
    COUNT(t.transaction_id)             AS total_transactions,
    ROUND(SUM(t.amount), 2)             AS total_spent,
    ROUND(AVG(t.amount), 2)             AS avg_transaction,
    MAX(t.txn_timestamp)                AS last_transaction_at,
    SUM(t.is_anomaly)                   AS anomaly_count
FROM customers c
LEFT JOIN accounts a    ON a.customer_id  = c.customer_id
LEFT JOIN transactions t ON t.account_id = a.account_id
    AND t.txn_status = 'completed'
GROUP BY c.customer_id, c.full_name, c.segment, c.country,
         c.signup_date, c.account_status;



CREATE OR REPLACE VIEW vw_merchant_summary AS
SELECT
    m.merchant_id,
    m.merchant_name,
    m.merchant_category,
    m.country                           AS merchant_country,
    m.risk_category,
    COUNT(t.transaction_id)             AS txn_count,
    ROUND(SUM(t.amount), 2)             AS total_volume,
    ROUND(AVG(t.amount), 2)             AS avg_amount,
    COUNT(DISTINCT t.account_id)        AS unique_accounts,
    SUM(CASE WHEN t.txn_status = 'failed'    THEN 1 ELSE 0 END) AS failed_count,
    SUM(CASE WHEN t.txn_status = 'reversed'  THEN 1 ELSE 0 END) AS reversed_count,
    SUM(t.is_anomaly)                   AS anomaly_count
FROM merchants m
LEFT JOIN transactions t ON t.merchant_id = m.merchant_id
GROUP BY m.merchant_id, m.merchant_name, m.merchant_category,
         m.country, m.risk_category;


CREATE OR REPLACE VIEW vw_anomaly_investigation AS
SELECT
    s.score_id,
    s.transaction_id,
    s.model_run_id,
    s.anomaly_score,
    s.is_flagged,
    s.scored_at,
    t.txn_timestamp,
    t.amount,
    t.currency,
    t.txn_type,
    t.payment_channel,
    t.txn_status,
    t.country              AS txn_country,
    t.is_anomaly           AS ground_truth_label,
    t.anomaly_type         AS ground_truth_type,
    a.account_id,
    a.account_type,
    c.customer_id,
    c.full_name            AS customer_name,
    c.segment,
    m.merchant_name,
    m.merchant_category,
    m.risk_category,
    cat.category_name
FROM anomaly_scores s
INNER JOIN transactions t  ON t.transaction_id = s.transaction_id
INNER JOIN accounts a      ON a.account_id     = t.account_id
INNER JOIN customers c     ON c.customer_id    = a.customer_id
INNER JOIN merchants m     ON m.merchant_id    = t.merchant_id
INNER JOIN categories cat  ON cat.category_id  = t.category_id;
