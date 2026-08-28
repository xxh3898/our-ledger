package io.github.xxh3898.ourledger.transaction;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

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
}
