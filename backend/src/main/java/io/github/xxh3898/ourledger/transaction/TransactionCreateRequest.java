package io.github.xxh3898.ourledger.transaction;

import java.time.Instant;

public record TransactionCreateRequest(
        TransactionType type,
        Long amount,
        TransactionScope scope,
        Long ownerMemberId,
        Long payerMemberId,
        Long categoryId,
        Long accountId,
        Long sourceAccountId,
        Long destinationAccountId,
        Instant occurredAt,
        String memo,
        AdjustmentType adjustmentType,
        Long reversesTransactionId
) {
}
