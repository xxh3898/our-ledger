package io.github.xxh3898.ourledger.statistics;

import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.transaction.TransactionScope;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;

public record StatisticsResponse(
        Period period,
        Summary summary,
        Comparison comparison,
        List<Subject> subjects,
        List<CategoryBreakdown> categories,
        List<AccountBreakdown> accounts,
        List<MonthTrend> months
) {

    public record Period(LocalDate from, LocalDate to, String timezone) {
    }

    public record Summary(
            long incomeAmount,
            long netSpendingAmount,
            Long savingsAmount,
            BigDecimal savingsRate
    ) {
    }

    public record Comparison(
            LocalDate from,
            LocalDate to,
            long incomeAmount,
            long netSpendingAmount,
            Long savingsAmount,
            BigDecimal savingsRate,
            long incomeDifferenceAmount,
            long netSpendingDifferenceAmount,
            Long savingsDifferenceAmount,
            BigDecimal incomePercentChange,
            BigDecimal netSpendingPercentChange,
            BigDecimal savingsPercentChange,
            BigDecimal savingsRateDifferencePoints
    ) {
    }

    public record Member(Long memberId, Long userId, String displayName) {
    }

    public record Subject(
            TransactionScope scope,
            Member owner,
            long netSpendingAmount
    ) {
    }

    public record CategoryReference(
            Long id,
            String name,
            boolean archived
    ) {
    }

    public record CategoryBreakdown(
            CategoryReference category,
            long netSpendingAmount,
            BigDecimal shareRate
    ) {
    }

    public record AccountReference(
            Long id,
            String name,
            AccountType type,
            AccountNature nature,
            boolean archived
    ) {
    }

    public record AccountBreakdown(
            AccountReference account,
            long netSpendingAmount
    ) {
    }

    public record MonthTrend(
            YearMonth month,
            long incomeAmount,
            long netSpendingAmount,
            Long savingsAmount,
            BigDecimal savingsRate
    ) {
    }
}
