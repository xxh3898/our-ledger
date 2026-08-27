package io.github.xxh3898.ourledger.transaction;

import java.time.LocalDate;

public record TransactionFilter(
        LocalDate from,
        LocalDate to,
        TransactionType type,
        TransactionScope scope,
        Long ownerMemberId,
        Long categoryId,
        Long accountId
) {
}
