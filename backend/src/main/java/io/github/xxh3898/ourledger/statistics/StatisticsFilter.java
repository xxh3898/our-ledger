package io.github.xxh3898.ourledger.statistics;

import io.github.xxh3898.ourledger.transaction.TransactionScope;

import java.time.LocalDate;

public record StatisticsFilter(
        LocalDate from,
        LocalDate to,
        LocalDate compareFrom,
        LocalDate compareTo,
        TransactionScope scope,
        Long ownerMemberId
) {

    public boolean isAllScope() {
        return scope == null;
    }

    public boolean hasComparison() {
        return compareFrom != null && compareTo != null;
    }
}
