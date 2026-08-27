package io.github.xxh3898.ourledger.transaction;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TransactionAccountEntryRepository
        extends JpaRepository<TransactionAccountEntry, Long> {

    Optional<TransactionAccountEntry> findByTransactionIdAndHouseholdIdAndEntryRole(
            Long transactionId,
            Long householdId,
            EntryRole entryRole
    );

    long countByTransactionId(Long transactionId);
}
