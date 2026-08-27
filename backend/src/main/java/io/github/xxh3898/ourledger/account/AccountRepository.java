package io.github.xxh3898.ourledger.account;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface AccountRepository extends JpaRepository<Account, Long> {

    List<Account> findAllByHouseholdIdOrderBySortOrderAscIdAsc(Long householdId);

    List<Account> findAllByHouseholdIdAndArchivedAtIsNullOrderBySortOrderAscIdAsc(Long householdId);

    Optional<Account> findByIdAndHouseholdId(Long id, Long householdId);

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
}
