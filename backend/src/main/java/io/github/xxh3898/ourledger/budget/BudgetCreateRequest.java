package io.github.xxh3898.ourledger.budget;

import java.time.YearMonth;

public record BudgetCreateRequest(
        YearMonth month,
        BudgetScope scope,
        Long ownerMemberId,
        Long categoryId,
        Long amount
) {
}
