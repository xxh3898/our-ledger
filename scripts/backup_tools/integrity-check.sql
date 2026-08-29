\set ON_ERROR_STOP on

DO $$
BEGIN
    BEGIN
        INSERT INTO transaction_account_entries (
            id,
            household_id,
            transaction_id,
            account_id,
            entry_role,
            balance_delta
        )
        VALUES (5998, 9999, 5004, 4101, 'PRIMARY', 1);
        RAISE EXCEPTION 'cross-Household composite FK accepted invalid Entry';
    EXCEPTION
        WHEN foreign_key_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO transaction_account_entries (
            id,
            household_id,
            transaction_id,
            account_id,
            entry_role,
            balance_delta
        )
        VALUES (5999, 2001, 5001, 4102, 'PRIMARY', 1);
        RAISE EXCEPTION 'transaction Entry role unique accepted duplicate';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;

    BEGIN
        INSERT INTO goal_accounts (
            goal_id,
            account_id,
            household_id,
            starting_balance,
            linked_at,
            linked_by
        )
        VALUES (8001, 4102, 2001, 230000, CURRENT_TIMESTAMP, 3001);
        RAISE EXCEPTION 'Goal Account unique accepted duplicate';
    EXCEPTION
        WHEN unique_violation THEN NULL;
    END;
END
$$;
