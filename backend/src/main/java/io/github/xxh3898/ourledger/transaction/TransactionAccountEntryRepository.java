package io.github.xxh3898.ourledger.transaction;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Set;

public interface TransactionAccountEntryRepository
        extends JpaRepository<TransactionAccountEntry, Long> {

    List<TransactionAccountEntry> findAllByTransactionIdAndHouseholdId(
            Long transactionId,
            Long householdId
    );

    List<TransactionAccountEntry>
            findAllByHouseholdIdAndTransactionIdInOrderByTransactionIdAscIdAsc(
                    Long householdId,
                    Set<Long> transactionIds
            );

    @Modifying
    @Query("""
            DELETE FROM TransactionAccountEntry entry
            WHERE entry.transactionId = :transactionId
              AND entry.householdId = :householdId
            """)
    int deleteAllForTransaction(
            @Param("transactionId") Long transactionId,
            @Param("householdId") Long householdId
    );

    long countByTransactionId(Long transactionId);

    @Query(value = """
            SELECT entry.account_id AS "accountId",
                   SUM(entry.balance_delta) AS "ledgerDelta"
            FROM transaction_account_entries entry
            JOIN transactions ledger_transaction
              ON ledger_transaction.id = entry.transaction_id
             AND ledger_transaction.household_id = entry.household_id
            WHERE entry.household_id = :householdId
              AND ledger_transaction.deleted_at IS NULL
              AND ledger_transaction.occurred_at < :beforeExclusive
            GROUP BY entry.account_id
            ORDER BY entry.account_id
            """, nativeQuery = true)
    List<AccountDelta> sumActiveBalanceDeltasBefore(
            @Param("householdId") Long householdId,
            @Param("beforeExclusive") Instant beforeExclusive
    );

    @Query(value = """
            SELECT entry.account_id AS "accountId",
                   CAST(DATE_TRUNC(
                       'month',
                       ledger_transaction.occurred_at AT TIME ZONE :timezone
                   ) AS date) AS "month",
                   SUM(entry.balance_delta) AS "ledgerDelta"
            FROM transaction_account_entries entry
            JOIN transactions ledger_transaction
              ON ledger_transaction.id = entry.transaction_id
             AND ledger_transaction.household_id = entry.household_id
            WHERE entry.household_id = :householdId
              AND ledger_transaction.deleted_at IS NULL
              AND ledger_transaction.occurred_at >= :fromInclusive
              AND ledger_transaction.occurred_at < :toExclusive
            GROUP BY entry.account_id, 2
            ORDER BY "month", "accountId"
            """, nativeQuery = true)
    List<AccountMonthlyDelta> sumActiveBalanceDeltasByLocalMonth(
            @Param("householdId") Long householdId,
            @Param("fromInclusive") Instant fromInclusive,
            @Param("toExclusive") Instant toExclusive,
            @Param("timezone") String timezone
    );

    interface AccountDelta {

        Long getAccountId();

        Long getLedgerDelta();
    }

    interface AccountMonthlyDelta {

        Long getAccountId();

        LocalDate getMonth();

        Long getLedgerDelta();
    }
}
