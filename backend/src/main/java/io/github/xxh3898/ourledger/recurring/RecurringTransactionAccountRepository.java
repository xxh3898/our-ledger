package io.github.xxh3898.ourledger.recurring;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface RecurringTransactionAccountRepository
        extends JpaRepository<RecurringTransactionAccount, Long> {

    List<RecurringTransactionAccount>
            findAllByRecurringTransactionIdAndHouseholdIdOrderByEntryRoleAsc(
                    Long recurringTransactionId,
                    Long householdId
            );

    @Modifying
    @Query("""
            DELETE FROM RecurringTransactionAccount account
            WHERE account.recurringTransactionId = :recurringId
              AND account.householdId = :householdId
            """)
    int deleteAllForRule(
            @Param("recurringId") Long recurringId,
            @Param("householdId") Long householdId
    );

    @Query(value = """
            SELECT recurring.type AS "transactionType", account.entry_role AS "entryRole"
            FROM recurring_transaction_accounts account
            JOIN recurring_transactions recurring
              ON recurring.id = account.recurring_transaction_id
             AND recurring.household_id = account.household_id
            WHERE account.household_id = :householdId
              AND account.account_id = :accountId
              AND recurring.active
              AND recurring.next_recurrence_date IS NOT NULL
            """, nativeQuery = true)
    List<ActiveAccountUsage> findActiveUsages(
            @Param("householdId") Long householdId,
            @Param("accountId") Long accountId
    );

    interface ActiveAccountUsage {
        String getTransactionType();
        String getEntryRole();
    }
}
