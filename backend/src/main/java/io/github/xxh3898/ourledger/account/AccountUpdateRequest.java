package io.github.xxh3898.ourledger.account;

import java.time.LocalDate;

public record AccountUpdateRequest(
        String name,
        String institution,
        AccountType type,
        AccountNature nature,
        AccountOwnership ownership,
        Long ownerMemberId,
        Long openingBalance,
        LocalDate openingBalanceAsOf,
        String currency,
        String lastFour,
        Boolean savingsEnabled,
        Integer sortOrder,
        Boolean archived
) {
}
