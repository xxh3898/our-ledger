package io.github.xxh3898.ourledger.transaction;

import java.time.Instant;

public record TransactionUpdateRequest(
        Long version,
        TransactionType type,
        Long amount,
        TransactionScope scope,
        Long ownerMemberId,
        Long payerMemberId,
        Long categoryId,
        Long accountId,
        Instant occurredAt,
        String memo,
        AdjustmentType adjustmentType,
        Long reversesTransactionId
) {
}
