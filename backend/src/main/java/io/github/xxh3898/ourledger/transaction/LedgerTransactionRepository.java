package io.github.xxh3898.ourledger.transaction;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.Optional;

public interface LedgerTransactionRepository
        extends JpaRepository<LedgerTransaction, Long>,
        JpaSpecificationExecutor<LedgerTransaction> {

    Optional<LedgerTransaction> findByIdAndHouseholdIdAndDeletedAtIsNull(
            Long id,
            Long householdId
    );
}
