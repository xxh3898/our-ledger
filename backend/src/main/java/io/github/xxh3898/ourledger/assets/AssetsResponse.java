package io.github.xxh3898.ourledger.assets;

import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountType;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;

public record AssetsResponse(
        Instant asOf,
        String timezone,
        Summary household,
        List<MemberSummary> members,
        Summary shared,
        List<AccountRow> accounts,
        List<MonthlyTrend> monthlyTrend
) {

    public record Summary(
            long totalAssets,
            long totalLiabilities,
            long netWorth
    ) {
    }

    public record MemberSummary(
            Long memberId,
            String displayName,
            long totalAssets,
            long totalLiabilities,
            long netWorth
    ) {
    }

    public record AccountRow(
            Long id,
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Owner owner,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            long ledgerDelta,
            long currentBalance,
            String currency,
            boolean savingsEnabled,
            boolean archived,
            int sortOrder
    ) {
    }

    public record Owner(
            Long memberId,
            String displayName
    ) {
    }

    public record MonthlyTrend(
            YearMonth month,
            boolean complete,
            Instant asOf,
            long assets,
            long liabilities,
            long netWorth
    ) {
    }
}
