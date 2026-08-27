package io.github.xxh3898.ourledger.transaction;

import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.category.CategoryType;

import java.time.Instant;
import java.util.List;

public record TransactionResponse(
        Long id,
        TransactionType type,
        long amount,
        TransactionScope scope,
        Member owner,
        Member payer,
        CategoryReference category,
        Instant occurredAt,
        String memo,
        AdjustmentType adjustmentType,
        long version,
        List<Entry> entries,
        Instant createdAt,
        Instant updatedAt
) {

    public record Member(Long memberId, Long userId, String displayName) {
    }

    public record CategoryReference(Long id, String name, CategoryType type, boolean archived) {
    }

    public record AccountReference(
            Long id,
            String name,
            AccountType type,
            AccountNature nature,
            boolean archived
    ) {
    }

    public record Entry(
            Long id,
            EntryRole role,
            long balanceDelta,
            AccountReference account
    ) {
    }
}
