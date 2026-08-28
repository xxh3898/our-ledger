package io.github.xxh3898.ourledger.transaction;

import java.time.Instant;
import java.time.LocalDate;

public record GeneratedTransactionCommand(
        Long householdId,
        Long recurringTransactionId,
        LocalDate recurrenceDate,
        TransactionType type,
        long amount,
        TransactionScope scope,
        Long ownerMemberId,
        Long payerMemberId,
        Long categoryId,
        Long accountId,
        Long sourceAccountId,
        Long destinationAccountId,
        Instant occurredAt,
        String memo,
        Long actorMemberId
) {
}
