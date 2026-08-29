\set ON_ERROR_STOP on
WITH account_balances AS (
    SELECT
        account.id,
        account.nature,
        account.opening_balance
            + COALESCE(
                SUM(entry.balance_delta) FILTER (
                    WHERE ledger_transaction.deleted_at IS NULL
                ),
                0
            ) AS current_balance
    FROM accounts account
    LEFT JOIN transaction_account_entries entry
        ON entry.account_id = account.id
       AND entry.household_id = account.household_id
    LEFT JOIN transactions ledger_transaction
        ON ledger_transaction.id = entry.transaction_id
       AND ledger_transaction.household_id = entry.household_id
    WHERE account.household_id = 2001
    GROUP BY account.id, account.nature, account.opening_balance
),
financial_summary AS (
    SELECT
        SUM(current_balance) FILTER (WHERE nature = 'ASSET') AS total_assets,
        SUM(current_balance) FILTER (WHERE nature = 'LIABILITY') AS total_liabilities
    FROM account_balances
),
row_counts AS (
    SELECT JSONB_BUILD_OBJECT(
        'users', (SELECT COUNT(*) FROM users),
        'households', (SELECT COUNT(*) FROM households),
        'householdMembers', (SELECT COUNT(*) FROM household_members),
        'accounts', (SELECT COUNT(*) FROM accounts),
        'categoryGroups', (SELECT COUNT(*) FROM category_groups),
        'categories', (SELECT COUNT(*) FROM categories),
        'transactions', (SELECT COUNT(*) FROM transactions),
        'transactionAccountEntries', (SELECT COUNT(*) FROM transaction_account_entries),
        'budgets', (SELECT COUNT(*) FROM budgets),
        'recurringTransactions', (SELECT COUNT(*) FROM recurring_transactions),
        'recurringTransactionAccounts', (SELECT COUNT(*) FROM recurring_transaction_accounts),
        'goals', (SELECT COUNT(*) FROM goals),
        'goalAccounts', (SELECT COUNT(*) FROM goal_accounts)
    ) AS value
),
transaction_evidence AS (
    SELECT STRING_AGG(
        CONCAT_WS(
            ':',
            id,
            type,
            amount,
            adjustment_type,
            COALESCE(reverses_transaction_id::TEXT, 'null')
        ),
        ',' ORDER BY id
    ) AS value
    FROM transactions
    WHERE household_id = 2001
),
entry_evidence AS (
    SELECT STRING_AGG(
        CONCAT_WS(':', transaction_id, account_id, entry_role, balance_delta),
        ',' ORDER BY id
    ) AS value
    FROM transaction_account_entries
    WHERE household_id = 2001
)
SELECT JSONB_BUILD_OBJECT(
    'flywayVersions', (
        SELECT STRING_AGG(version, ',' ORDER BY installed_rank)
        FROM flyway_schema_history
        WHERE success
    ),
    'rowCounts', (SELECT value FROM row_counts),
    'checkingBalance', (
        SELECT current_balance FROM account_balances WHERE id = 4101
    ),
    'savingsBalance', (
        SELECT current_balance FROM account_balances WHERE id = 4102
    ),
    'liabilityBalance', (
        SELECT current_balance FROM account_balances WHERE id = 4103
    ),
    'totalAssets', (SELECT total_assets FROM financial_summary),
    'totalLiabilities', (SELECT total_liabilities FROM financial_summary),
    'netWorth', (
        SELECT total_assets - total_liabilities FROM financial_summary
    ),
    'refundLineageCount', (
        SELECT COUNT(*)
        FROM transactions
        WHERE household_id = 2001
          AND adjustment_type = 'REFUND'
          AND reverses_transaction_id = 5002
    ),
    'transferEntryCount', (
        SELECT COUNT(*)
        FROM transaction_account_entries
        WHERE household_id = 2001
          AND transaction_id = 5004
          AND entry_role IN ('SOURCE', 'DESTINATION')
    ),
    'transactionEvidence', (SELECT value FROM transaction_evidence),
    'entryEvidence', (SELECT value FROM entry_evidence),
    'goalStartingBalance', (
        SELECT starting_balance
        FROM goal_accounts
        WHERE goal_id = 8001 AND account_id = 4102
    )
);
