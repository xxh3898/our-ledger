package io.github.xxh3898.ourledger.account;

import java.time.Instant;
import java.time.LocalDate;

public record AccountResponse(
        Long id,
        String name,
        String institution,
        AccountType type,
        AccountNature nature,
        AccountOwnership ownership,
        Owner owner,
        long openingBalance,
        LocalDate openingBalanceAsOf,
        long currentBalance,
        String currency,
        String lastFour,
        boolean savingsEnabled,
        int sortOrder,
        boolean archived,
        Instant createdAt,
        Instant updatedAt
) {

    public record Owner(Long memberId, Long userId, String displayName) {
    }
}
