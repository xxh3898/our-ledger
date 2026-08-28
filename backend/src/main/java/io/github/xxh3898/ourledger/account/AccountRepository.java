package io.github.xxh3898.ourledger.account;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface AccountRepository extends JpaRepository<Account, Long> {

    List<Account> findAllByHouseholdIdOrderBySortOrderAscIdAsc(Long householdId);

    List<Account> findAllByHouseholdIdAndArchivedAtIsNullOrderBySortOrderAscIdAsc(Long householdId);

    Optional<Account> findByIdAndHouseholdId(Long id, Long householdId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT account
            FROM Account account
            WHERE account.id = :accountId
              AND account.householdId = :householdId
            """)
    Optional<Account> findByIdAndHouseholdIdForUpdate(
            @Param("accountId") Long accountId,
            @Param("householdId") Long householdId
    );

    @Query(value = """
            SELECT EXISTS (
                SELECT 1
                FROM transaction_account_entries entry
                WHERE entry.household_id = :householdId
                  AND entry.account_id = :accountId
            )
            """, nativeQuery = true)
    boolean hasLedgerEntries(
            @Param("householdId") Long householdId,
            @Param("accountId") Long accountId
    );

    @Query(value = """
            SELECT COALESCE(SUM(entry.balance_delta), 0)
            FROM transaction_account_entries entry
            JOIN transactions ledger_transaction
              ON ledger_transaction.id = entry.transaction_id
             AND ledger_transaction.household_id = entry.household_id
            WHERE entry.household_id = :householdId
              AND entry.account_id = :accountId
              AND ledger_transaction.deleted_at IS NULL
            """, nativeQuery = true)
    Long sumActiveBalanceDelta(
            @Param("householdId") Long householdId,
            @Param("accountId") Long accountId
    );

    @Query(value = """
            SELECT entry.account_id AS "accountId",
                   SUM(entry.balance_delta) AS "ledgerDelta"
            FROM transaction_account_entries entry
            JOIN transactions ledger_transaction
              ON ledger_transaction.id = entry.transaction_id
             AND ledger_transaction.household_id = entry.household_id
            WHERE entry.household_id = :householdId
              AND ledger_transaction.deleted_at IS NULL
            GROUP BY entry.account_id
            ORDER BY entry.account_id
            """, nativeQuery = true)
    List<AccountBalanceDelta> sumActiveBalanceDeltas(
            @Param("householdId") Long householdId
    );

    interface AccountBalanceDelta {

        Long getAccountId();

        Long getLedgerDelta();
    }
}
