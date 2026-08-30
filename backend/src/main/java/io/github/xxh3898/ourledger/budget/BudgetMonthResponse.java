package io.github.xxh3898.ourledger.budget;

import java.time.YearMonth;
import java.util.List;

public record BudgetMonthResponse(
        YearMonth month,
        String timezone,
        List<ScopeBudget> scopes,
        List<CategoryBudget> categories
) {

    public BudgetMonthResponse {
        scopes = List.copyOf(scopes);
        categories = List.copyOf(categories);
    }

    public record ScopeBudget(
            BudgetScope scope,
            BudgetResponse.Member owner,
            Long budgetId,
            Long version,
            Long budgetAmount,
            long spentAmount,
            Long remainingAmount,
            boolean exceeded
    ) {
    }

    public record CategoryBudget(
            Long budgetId,
            long version,
            BudgetScope scope,
            BudgetResponse.Member owner,
            BudgetResponse.CategoryReference category,
            long budgetAmount,
            long spentAmount,
            long remainingAmount,
            boolean exceeded
    ) {
    }
}
