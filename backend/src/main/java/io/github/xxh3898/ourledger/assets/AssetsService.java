package io.github.xxh3898.ourledger.assets;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountBalanceService;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class AssetsService {

    private static final int COMPLETED_TREND_MONTHS = 11;

    private final AccountRepository accountRepository;
    private final AccountBalanceService accountBalanceService;
    private final TransactionAccountEntryRepository entryRepository;
    private final HouseholdMemberRepository memberRepository;
    private final Clock clock;

    public AssetsService(
            AccountRepository accountRepository,
            AccountBalanceService accountBalanceService,
            TransactionAccountEntryRepository entryRepository,
            HouseholdMemberRepository memberRepository,
            Clock clock
    ) {
        this.accountRepository = accountRepository;
        this.accountBalanceService = accountBalanceService;
        this.entryRepository = entryRepository;
        this.memberRepository = memberRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
    public AssetsResponse find(CurrentHousehold currentHousehold) {
        Long householdId = currentHousehold.householdId();
        Instant asOf = clock.instant();
        List<HouseholdMember> members = memberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(householdId);
        Map<Long, HouseholdMember> membersById = members.stream().collect(Collectors.toMap(
                HouseholdMember::getId,
                Function.identity()
        ));
        Map<Long, Integer> memberOrder = new LinkedHashMap<>();
        for (int index = 0; index < members.size(); index++) {
            memberOrder.put(members.get(index).getId(), index);
        }

        List<Account> accounts = new ArrayList<>(
                accountRepository.findAllByHouseholdIdOrderBySortOrderAscIdAsc(householdId));
        validateOwners(accounts, membersById);
        accounts.sort(accountComparator(memberOrder, members.size()));
        Map<Long, AccountBalanceService.AccountBalance> balances =
                accountBalanceService.currentBalances(accounts);
        List<AssetsResponse.AccountRow> rows = accounts.stream()
                .map(account -> toRow(account, membersById, balances.get(account.getId())))
                .toList();

        AssetsResponse.Summary household = summary(rows);
        List<AssetsResponse.MemberSummary> memberSummaries = members.stream()
                .map(member -> memberSummary(member, rows))
                .toList();
        AssetsResponse.Summary shared = summary(rows.stream()
                .filter(row -> row.ownership() == AccountOwnership.SHARED)
                .toList());
        List<AssetsResponse.MonthlyTrend> trend = trend(
                currentHousehold,
                accounts,
                household,
                asOf
        );

        return new AssetsResponse(
                asOf,
                currentHousehold.timezone(),
                household,
                memberSummaries,
                shared,
                rows,
                trend
        );
    }

    private void validateOwners(
            List<Account> accounts,
            Map<Long, HouseholdMember> membersById
    ) {
        boolean invalidOwner = accounts.stream()
                .filter(account -> account.getOwnership() == AccountOwnership.PERSONAL)
                .anyMatch(account -> !membersById.containsKey(account.getOwnerMemberId()));
        if (invalidOwner) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.RESOURCE_STATE_CONFLICT
            );
        }
    }

    private Comparator<Account> accountComparator(
            Map<Long, Integer> memberOrder,
            int sharedOrder
    ) {
        return Comparator
                .comparingInt((Account account) -> account.getNature() == AccountNature.ASSET
                        ? 0 : 1)
                .thenComparingInt(account -> account.getOwnership() == AccountOwnership.PERSONAL
                        ? memberOrder.get(account.getOwnerMemberId()) : sharedOrder)
                .thenComparingInt(Account::getSortOrder)
                .thenComparing(Account::getId);
    }

    private AssetsResponse.AccountRow toRow(
            Account account,
            Map<Long, HouseholdMember> membersById,
            AccountBalanceService.AccountBalance balance
    ) {
        AssetsResponse.Owner owner = null;
        if (account.getOwnerMemberId() != null) {
            HouseholdMember member = membersById.get(account.getOwnerMemberId());
            owner = new AssetsResponse.Owner(
                    member.getId(),
                    member.getUser().getDisplayName()
            );
        }
        return new AssetsResponse.AccountRow(
                account.getId(),
                account.getName(),
                account.getInstitution(),
                account.getType(),
                account.getNature(),
                account.getOwnership(),
                owner,
                account.getOpeningBalance(),
                account.getOpeningBalanceAsOf(),
                balance.ledgerDelta(),
                balance.currentBalance(),
                account.getCurrency(),
                account.isSavingsEnabled(),
                account.isArchived(),
                account.getSortOrder()
        );
    }

    private AssetsResponse.MemberSummary memberSummary(
            HouseholdMember member,
            List<AssetsResponse.AccountRow> rows
    ) {
        AssetsResponse.Summary summary = summary(rows.stream()
                .filter(row -> row.ownership() == AccountOwnership.PERSONAL)
                .filter(row -> row.owner().memberId().equals(member.getId()))
                .toList());
        return new AssetsResponse.MemberSummary(
                member.getId(),
                member.getUser().getDisplayName(),
                summary.totalAssets(),
                summary.totalLiabilities(),
                summary.netWorth()
        );
    }

    private AssetsResponse.Summary summary(List<AssetsResponse.AccountRow> rows) {
        long assets = 0;
        long liabilities = 0;
        for (AssetsResponse.AccountRow row : rows) {
            if (row.nature() == AccountNature.ASSET) {
                assets = Math.addExact(assets, row.currentBalance());
            } else {
                liabilities = Math.addExact(liabilities, row.currentBalance());
            }
        }
        return summary(assets, liabilities);
    }

    private AssetsResponse.Summary summary(long assets, long liabilities) {
        return new AssetsResponse.Summary(
                assets,
                liabilities,
                Math.subtractExact(assets, liabilities)
        );
    }

    private List<AssetsResponse.MonthlyTrend> trend(
            CurrentHousehold currentHousehold,
            List<Account> accounts,
            AssetsResponse.Summary currentSummary,
            Instant asOf
    ) {
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        YearMonth currentMonth = YearMonth.now(clock.withZone(zoneId));
        YearMonth firstMonth = currentMonth.minusMonths(COMPLETED_TREND_MONTHS);
        Instant firstCutoff = firstMonth.plusMonths(1)
                .atDay(1)
                .atStartOfDay(zoneId)
                .toInstant();
        Instant currentMonthStart = currentMonth
                .atDay(1)
                .atStartOfDay(zoneId)
                .toInstant();

        Map<Long, Long> cumulativeDeltas = new LinkedHashMap<>();
        for (TransactionAccountEntryRepository.AccountDelta item
                : entryRepository.sumActiveBalanceDeltasBefore(
                        currentHousehold.householdId(), firstCutoff)) {
            cumulativeDeltas.put(item.getAccountId(), item.getLedgerDelta());
        }
        Map<YearMonth, Map<Long, Long>> monthlyDeltas = new LinkedHashMap<>();
        for (TransactionAccountEntryRepository.AccountMonthlyDelta item
                : entryRepository.sumActiveBalanceDeltasByLocalMonth(
                        currentHousehold.householdId(),
                        firstCutoff,
                        currentMonthStart,
                        currentHousehold.timezone())) {
            monthlyDeltas.computeIfAbsent(
                    YearMonth.from(item.getMonth()),
                    ignored -> new LinkedHashMap<>()
            ).put(item.getAccountId(), item.getLedgerDelta());
        }

        List<AssetsResponse.MonthlyTrend> result = new ArrayList<>();
        for (int index = 0; index < COMPLETED_TREND_MONTHS; index++) {
            YearMonth month = firstMonth.plusMonths(index);
            if (index > 0) {
                monthlyDeltas.getOrDefault(month, Map.of()).forEach(
                        (accountId, delta) -> cumulativeDeltas.merge(
                                accountId,
                                delta,
                                Math::addExact
                        )
                );
            }
            AssetsResponse.Summary summary = historicalSummary(
                    accounts,
                    cumulativeDeltas,
                    month
            );
            Instant monthEnd = month.plusMonths(1)
                    .atDay(1)
                    .atStartOfDay(zoneId)
                    .toInstant()
                    .minusNanos(1);
            result.add(new AssetsResponse.MonthlyTrend(
                    month,
                    true,
                    monthEnd,
                    summary.totalAssets(),
                    summary.totalLiabilities(),
                    summary.netWorth()
            ));
        }
        result.add(new AssetsResponse.MonthlyTrend(
                currentMonth,
                false,
                asOf,
                currentSummary.totalAssets(),
                currentSummary.totalLiabilities(),
                currentSummary.netWorth()
        ));
        return List.copyOf(result);
    }

    private AssetsResponse.Summary historicalSummary(
            List<Account> accounts,
            Map<Long, Long> cumulativeDeltas,
            YearMonth month
    ) {
        long assets = 0;
        long liabilities = 0;
        for (Account account : accounts) {
            long contribution = month.atEndOfMonth().isBefore(account.getOpeningBalanceAsOf())
                    ? 0
                    : Math.addExact(
                            account.getOpeningBalance(),
                            cumulativeDeltas.getOrDefault(account.getId(), 0L)
                    );
            if (account.getNature() == AccountNature.ASSET) {
                assets = Math.addExact(assets, contribution);
            } else {
                liabilities = Math.addExact(liabilities, contribution);
            }
        }
        return summary(assets, liabilities);
    }
}
