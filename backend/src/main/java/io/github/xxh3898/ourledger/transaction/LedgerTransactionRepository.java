package io.github.xxh3898.ourledger.transaction;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface LedgerTransactionRepository
        extends JpaRepository<LedgerTransaction, Long>,
        JpaSpecificationExecutor<LedgerTransaction> {

    Optional<LedgerTransaction> findByIdAndHouseholdIdAndDeletedAtIsNull(
            Long id,
            Long householdId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT ledgerTransaction
            FROM LedgerTransaction ledgerTransaction
            WHERE ledgerTransaction.id = :transactionId
              AND ledgerTransaction.householdId = :householdId
              AND ledgerTransaction.deletedAt IS NULL
            """)
    Optional<LedgerTransaction> findActiveByIdAndHouseholdIdForUpdate(
            @Param("transactionId") Long transactionId,
            @Param("householdId") Long householdId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT ledgerTransaction
            FROM LedgerTransaction ledgerTransaction
            WHERE ledgerTransaction.id = :transactionId
              AND ledgerTransaction.householdId = :householdId
            """)
    Optional<LedgerTransaction> findByIdAndHouseholdIdForUpdate(
            @Param("transactionId") Long transactionId,
            @Param("householdId") Long householdId
    );

    List<LedgerTransaction>
            findAllByHouseholdIdAndReversesTransactionIdAndAdjustmentTypeAndDeletedAtIsNullOrderByOccurredAtDescIdDesc(
                    Long householdId,
                    Long reversesTransactionId,
                    AdjustmentType adjustmentType
            );

    boolean existsByHouseholdIdAndReversesTransactionIdAndAdjustmentTypeAndDeletedAtIsNull(
            Long householdId,
            Long reversesTransactionId,
            AdjustmentType adjustmentType
    );

    boolean existsByGeneratedFromRecurringIdAndRecurrenceDate(
            Long generatedFromRecurringId,
            java.time.LocalDate recurrenceDate
    );

    List<LedgerTransaction>
            findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                    Long householdId,
                    Instant fromInclusive,
                    Instant toExclusive
            );

    List<LedgerTransaction>
            findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThanOrderByOccurredAtAscIdAsc(
                    Long householdId,
                    Instant fromInclusive,
                    Instant toExclusive
            );

    List<LedgerTransaction>
            findAllByHouseholdIdAndTypeAndDeletedAtIsNullOrderByOccurredAtDescIdDesc(
                    Long householdId,
                    TransactionType type
            );
}
