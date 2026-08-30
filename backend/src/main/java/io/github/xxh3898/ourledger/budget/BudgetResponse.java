package io.github.xxh3898.ourledger.budget;

import io.github.xxh3898.ourledger.category.CategoryType;

import java.time.Instant;
import java.time.YearMonth;

public record BudgetResponse(
        Long id,
        YearMonth month,
        BudgetScope scope,
        Member owner,
        CategoryReference category,
        long amount,
        long version,
        Instant createdAt,
        Instant updatedAt
) {

    public record Member(Long memberId, Long userId, String displayName) {
    }

    public record CategoryReference(
            Long id,
            String name,
            CategoryType type,
            boolean archived
    ) {
    }
}
