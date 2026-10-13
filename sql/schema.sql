-- sql/schema.sql — Financial Transaction Intelligence Database Schema
-- =======================================================================
-- Design principles:
--   1. DECIMAL for money: FLOAT/DOUBLE have rounding errors. DECIMAL(15,2)
--      stores exact monetary values up to 999,999,999,999,999.99.
--   2. Surrogate integer PKs: Simple, fast to join, predictable index size.
--   3. Foreign key constraints: MySQL enforces referential integrity at the
--      database level — a transaction cannot reference a non-existent account.
--   4. Indexes: Only on columns that appear in WHERE, JOIN ON, or ORDER BY
--      clauses for actual queries. See index comments for reasoning.
--   5. IF NOT EXISTS: Schema creation is idempotent — running it twice is safe.
-- =======================================================================

-- Use the existing database (do not DROP/CREATE)
USE financial_transaction;

-- ── 1. customers ──────────────────────────────────────────────────────────────
-- One customer can have multiple accounts (one-to-many → accounts).
CREATE TABLE IF NOT EXISTS customers (
    customer_id    INT            NOT NULL AUTO_INCREMENT,
    full_name      VARCHAR(120)   NOT NULL,
    email          VARCHAR(200)   NOT NULL,
    signup_date    DATE           NOT NULL,
    country        VARCHAR(60)    NOT NULL,
    segment        ENUM('retail','premium','business','vip') NOT NULL DEFAULT 'retail',
    account_status ENUM('active','inactive','suspended')     NOT NULL DEFAULT 'active',
    created_at     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email),
    -- Queries filter by country (analytics) and segment (cohort analysis)
    INDEX idx_customers_country (country),
    INDEX idx_customers_segment (segment),
    INDEX idx_customers_signup  (signup_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 2. accounts ───────────────────────────────────────────────────────────────
-- Each account belongs to exactly one customer.
-- Transactions are linked to accounts, not customers directly — this lets one
-- customer have a savings account and a business account with separate histories.
CREATE TABLE IF NOT EXISTS accounts (
    account_id     INT            NOT NULL AUTO_INCREMENT,
    customer_id    INT            NOT NULL,
    account_type   ENUM('checking','savings','business','investment') NOT NULL,
    currency       CHAR(3)        NOT NULL DEFAULT 'USD',
    account_status ENUM('active','dormant','closed')                 NOT NULL DEFAULT 'active',
    opening_date   DATE           NOT NULL,
    created_at     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (account_id),
    CONSTRAINT fk_accounts_customer
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    -- Used in JOINs from transactions → accounts → customers
    INDEX idx_accounts_customer  (customer_id),
    INDEX idx_accounts_currency  (currency),
    INDEX idx_accounts_type      (account_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 3. merchants ──────────────────────────────────────────────────────────────
-- 100 merchants that appear in transactions.
-- risk_category lets the anomaly dashboard highlight high-risk merchants.
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id       INT           NOT NULL AUTO_INCREMENT,
    merchant_name     VARCHAR(120)  NOT NULL,
    merchant_category VARCHAR(80)   NOT NULL,
    country           VARCHAR(60)   NOT NULL,
    risk_category     ENUM('low','medium','high') NOT NULL DEFAULT 'low',
    created_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (merchant_id),
    INDEX idx_merchants_category (merchant_category),
    INDEX idx_merchants_risk     (risk_category),
    INDEX idx_merchants_country  (country)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 4. categories ─────────────────────────────────────────────────────────────
-- 15–30 spending categories (e.g., groceries, travel, ATM).
-- Kept separate so categories can be managed centrally.
CREATE TABLE IF NOT EXISTS categories (
    category_id   INT          NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(80)  NOT NULL,
    description   VARCHAR(255) NOT NULL DEFAULT '',

    PRIMARY KEY (category_id),
    UNIQUE KEY uq_category_name (category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 5. transactions ───────────────────────────────────────────────────────────
-- Central fact table. ~100k rows expected.
-- is_anomaly is the SYNTHETIC GROUND-TRUTH label injected by the data generator.
-- The ML model must NOT use this column as a feature.
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id   BIGINT         NOT NULL AUTO_INCREMENT,
    account_id       INT            NOT NULL,
    merchant_id      INT            NOT NULL,
    category_id      INT            NOT NULL,
    txn_timestamp    DATETIME       NOT NULL,
    amount           DECIMAL(15,2)  NOT NULL,
    currency         CHAR(3)        NOT NULL DEFAULT 'USD',
    txn_type         ENUM('purchase','refund','transfer','withdrawal','deposit') NOT NULL,
    payment_channel  ENUM('card_online','card_pos','bank_transfer','mobile_app','atm') NOT NULL,
    txn_status       ENUM('completed','failed','pending','reversed') NOT NULL DEFAULT 'completed',
    country          VARCHAR(60)    NOT NULL,
    is_anomaly       TINYINT(1)     NOT NULL DEFAULT 0,  -- 1 = injected anomaly
    anomaly_type     VARCHAR(80)    NULL,                -- describes the injection
    created_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (transaction_id),
    CONSTRAINT fk_txn_account   FOREIGN KEY (account_id)   REFERENCES accounts(account_id)     ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_txn_merchant  FOREIGN KEY (merchant_id)  REFERENCES merchants(merchant_id)   ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_txn_category  FOREIGN KEY (category_id)  REFERENCES categories(category_id)  ON DELETE RESTRICT ON UPDATE CASCADE,

    -- Most queries filter by time range — this is the most important index
    INDEX idx_txn_timestamp   (txn_timestamp),
    -- JOINs from transaction → account and then → customer
    INDEX idx_txn_account     (account_id),
    INDEX idx_txn_merchant    (merchant_id),
    INDEX idx_txn_category    (category_id),
    -- Dashboard filters
    INDEX idx_txn_status      (txn_status),
    INDEX idx_txn_is_anomaly  (is_anomaly),
    -- Composite: most dashboard queries filter by account + time together
    INDEX idx_txn_account_time (account_id, txn_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 6. anomaly_scores ─────────────────────────────────────────────────────────
-- Keeps model output SEPARATE from transaction facts.
-- This way re-running the model doesn't pollute the original data.
-- model_run_id groups all scores from a single training run.
CREATE TABLE IF NOT EXISTS anomaly_scores (
    score_id         BIGINT         NOT NULL AUTO_INCREMENT,
    transaction_id   BIGINT         NOT NULL,
    model_run_id     VARCHAR(40)    NOT NULL,  -- e.g., ISO timestamp or UUID
    anomaly_score    FLOAT          NOT NULL,  -- raw IF score (more negative = more anomalous)
    is_flagged       TINYINT(1)     NOT NULL DEFAULT 0,
    scored_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (score_id),
    CONSTRAINT fk_score_txn FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id) ON DELETE CASCADE,
    -- Prevents duplicate scores for the same transaction in the same run
    UNIQUE KEY uq_score_txn_run (transaction_id, model_run_id),
    INDEX idx_scores_run     (model_run_id),
    INDEX idx_scores_flagged (is_flagged),
    INDEX idx_scores_score   (anomaly_score)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ── 7. model_runs ─────────────────────────────────────────────────────────────
-- Audit log of every anomaly detection run with its parameters and results.
CREATE TABLE IF NOT EXISTS model_runs (
    run_id           VARCHAR(40)    NOT NULL,
    model_type       VARCHAR(40)    NOT NULL DEFAULT 'IsolationForest',
    contamination    FLOAT          NOT NULL,
    random_seed      INT            NOT NULL,
    n_transactions   INT            NOT NULL,
    n_flagged        INT            NOT NULL,
    precision_score  FLOAT          NULL,
    recall_score     FLOAT          NULL,
    f1_score         FLOAT          NULL,
    training_cutoff  DATETIME       NULL,  -- chronological split point
    artifact_path    VARCHAR(255)   NULL,
    notes            TEXT           NULL,
    created_at       TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
