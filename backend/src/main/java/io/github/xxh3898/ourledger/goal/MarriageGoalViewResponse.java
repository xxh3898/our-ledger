package io.github.xxh3898.ourledger.goal;

import io.github.xxh3898.ourledger.account.AccountOwnership;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;

public record MarriageGoalViewResponse(
        MarriageGoal goal,
        List<EligibleAccount> eligibleAccounts
) {

    public record MarriageGoal(
            Long id,
            GoalType type,
            String name,
            long targetAmount,
            long version,
            long currentAmount,
            BigDecimal achievementRate,
            long remainingAmount,
            long thisMonthSavingsAmount,
            Long recentAverageMonthlySavingsAmount,
            GoalProjectionStatus projectionStatus,
            YearMonth expectedAchievementMonth,
            List<MonthlyTrend> monthlyTrend,
            List<LinkedAccount> linkedAccounts,
            List<SavingsActivity> recentSavingsActivities,
            Instant createdAt,
            Instant updatedAt
    ) {
    }

    public record MonthlyTrend(
            YearMonth month,
            long savingsAmount
    ) {
    }

    public record LinkedAccount(
            Long id,
            String name,
            AccountOwnership ownership,
            Owner owner,
            long currentBalance,
            long startingBalance,
            Instant linkedAt,
            boolean archived
    ) {
    }

    public record EligibleAccount(
            Long id,
            String name,
            AccountOwnership ownership,
            Owner owner,
            long currentBalance
    ) {
    }

    public record Owner(
            Long memberId,
            String displayName
    ) {
    }

    public record SavingsActivity(
            Long transactionId,
            Instant occurredAt,
            long amount,
            long savingsImpactAmount,
            AccountReference sourceAccount,
            AccountReference destinationAccount,
            String memo,
            Long generatedFromRecurringId,
            LocalDate recurrenceDate
    ) {
    }

    public record AccountReference(
            Long id,
            String name
    ) {
    }
}
