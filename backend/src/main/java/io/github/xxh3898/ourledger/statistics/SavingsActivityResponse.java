package io.github.xxh3898.ourledger.statistics;

import java.time.OffsetDateTime;

public record SavingsActivityResponse(
        Long transactionId,
        OffsetDateTime occurredAt,
        long amount,
        long savingsImpactAmount,
        AccountReference sourceAccount,
        AccountReference destinationAccount,
        String memo
) {

    public record AccountReference(Long id, String name) {
    }
}
