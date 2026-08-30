\set ON_ERROR_STOP on

BEGIN;

INSERT INTO users (id, email, display_name, status)
VALUES
    (1001, 'backup-owner@example.test', 'Backup Owner', 'ACTIVE'),
    (1002, 'backup-member@example.test', 'Backup Member', 'ACTIVE');

INSERT INTO households (id, name, base_currency, timezone)
VALUES (2001, 'Synthetic Restore Household', 'KRW', 'Asia/Seoul');

INSERT INTO household_members (id, household_id, user_id, role)
VALUES
    (3001, 2001, 1001, 'OWNER'),
    (3002, 2001, 1002, 'MEMBER');

INSERT INTO accounts (
    id,
    household_id,
    name,
    institution,
    type,
    nature,
    ownership,
    owner_member_id,
    opening_balance,
    opening_balance_as_of,
    currency,
    last_four,
    savings_enabled,
    sort_order
)
VALUES
    (
        4101, 2001, 'Synthetic Checking', 'Fixture Bank', 'CHECKING', 'ASSET',
        'PERSONAL', 3001, 50000, DATE '2026-01-01', 'KRW', '1001', FALSE, 0
    ),
    (
        4102, 2001, 'Synthetic Savings', 'Fixture Bank', 'SAVINGS', 'ASSET',
        'SHARED', NULL, 200000, DATE '2026-01-01', 'KRW', '1002', TRUE, 1
    ),
    (
        4103, 2001, 'Synthetic Card', 'Fixture Card', 'CREDIT_CARD', 'LIABILITY',
        'SHARED', NULL, 0, DATE '2026-01-01', 'KRW', '1003', FALSE, 2
    );

INSERT INTO category_groups (id, household_id, name, type, sort_order)
VALUES
    (4201, 2001, 'Synthetic Income', 'INCOME', 0),
    (4202, 2001, 'Synthetic Expense', 'EXPENSE', 1);

INSERT INTO categories (
    id,
    household_id,
    group_id,
    name,
    type,
    icon_key,
    color_key,
    sort_order
)
VALUES
    (4301, 2001, 4201, 'Synthetic Salary', 'INCOME', 'fixture-income', 'green', 0),
    (4302, 2001, 4202, 'Synthetic Living', 'EXPENSE', 'fixture-expense', 'blue', 0);

INSERT INTO transactions (
    id,
    household_id,
    type,
    amount,
    scope,
    owner_member_id,
    payer_member_id,
    category_id,
    occurred_at,
    memo,
    adjustment_type,
    reverses_transaction_id,
    version,
    created_by,
    updated_by
)
VALUES
    (
        5001, 2001, 'INCOME', 100000, 'PERSONAL', 3001, NULL, 4301,
        TIMESTAMPTZ '2026-08-01 00:00:00+09', 'Synthetic income',
        'NORMAL', NULL, 0, 3001, 3001
    ),
    (
        5002, 2001, 'EXPENSE', 20000, 'SHARED', NULL, 3001, 4302,
        TIMESTAMPTZ '2026-08-02 12:00:00+09', 'Synthetic cash expense',
        'NORMAL', NULL, 0, 3001, 3001
    ),
    (
        5003, 2001, 'EXPENSE', 15000, 'SHARED', NULL, 3002, 4302,
        TIMESTAMPTZ '2026-08-03 12:00:00+09', 'Synthetic card expense',
        'NORMAL', NULL, 0, 3002, 3002
    ),
    (
        5004, 2001, 'TRANSFER', 30000, NULL, NULL, NULL, NULL,
        TIMESTAMPTZ '2026-08-04 12:00:00+09', 'Synthetic savings transfer',
        'NORMAL', NULL, 0, 3001, 3001
    ),
    (
        5005, 2001, 'EXPENSE', 5000, 'SHARED', NULL, 3001, 4302,
        TIMESTAMPTZ '2026-08-05 12:00:00+09', 'Synthetic partial refund',
        'REFUND', 5002, 0, 3001, 3001
    );

INSERT INTO transaction_account_entries (
    id,
    household_id,
    transaction_id,
    account_id,
    entry_role,
    balance_delta
)
VALUES
    (5101, 2001, 5001, 4101, 'PRIMARY', 100000),
    (5102, 2001, 5002, 4101, 'PRIMARY', -20000),
    (5103, 2001, 5003, 4103, 'PRIMARY', 15000),
    (5104, 2001, 5004, 4101, 'SOURCE', -30000),
    (5105, 2001, 5004, 4102, 'DESTINATION', 30000),
    (5106, 2001, 5005, 4101, 'PRIMARY', 5000);

INSERT INTO budgets (
    id,
    household_id,
    budget_month,
    scope,
    owner_member_id,
    category_id,
    amount,
    version
)
VALUES (6001, 2001, DATE '2026-08-01', 'SHARED', NULL, 4302, 300000, 0);

INSERT INTO recurring_transactions (
    id,
    household_id,
    name,
    type,
    amount,
    scope,
    owner_member_id,
    payer_member_id,
    category_id,
    memo,
    frequency,
    interval_value,
    start_date,
    end_date,
    scheduled_local_time,
    auto_post,
    active,
    next_recurrence_date,
    version,
    created_by,
    updated_by
)
VALUES (
    7001,
    2001,
    'Synthetic paused recurring expense',
    'EXPENSE',
    10000,
    'SHARED',
    NULL,
    3001,
    4302,
    'Synthetic recurring memo',
    'MONTHLY',
    1,
    DATE '2026-08-01',
    NULL,
    TIME '09:00:00',
    TRUE,
    FALSE,
    NULL,
    0,
    3001,
    3001
);

INSERT INTO recurring_transaction_accounts (
    id,
    household_id,
    recurring_transaction_id,
    account_id,
    entry_role
)
VALUES (7101, 2001, 7001, 4101, 'PRIMARY');

INSERT INTO goals (
    id,
    household_id,
    type,
    name,
    target_amount,
    version,
    created_by,
    updated_by
)
VALUES (8001, 2001, 'MARRIAGE', 'Synthetic Marriage Goal', 1000000, 0, 3001, 3001);

INSERT INTO goal_accounts (
    goal_id,
    account_id,
    household_id,
    starting_balance,
    linked_at,
    linked_by
)
VALUES (
    8001,
    4102,
    2001,
    230000,
    TIMESTAMPTZ '2026-08-04 13:00:00+09',
    3001
);

COMMIT;
