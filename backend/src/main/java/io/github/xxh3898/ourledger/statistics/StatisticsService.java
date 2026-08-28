package io.github.xxh3898.ourledger.statistics;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryGroup;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.NetSpendingCalculator;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntry;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class StatisticsService {

    private static final BigDecimal ONE_HUNDRED = BigDecimal.valueOf(100);

    private final LedgerTransactionRepository transactionRepository;
    private final TransactionAccountEntryRepository entryRepository;
    private final AccountRepository accountRepository;
    private final CategoryRepository categoryRepository;
    private final CategoryGroupRepository categoryGroupRepository;
    private final HouseholdMemberRepository householdMemberRepository;
    private final HouseholdMemberResolver householdMemberResolver;

    public StatisticsService(
            LedgerTransactionRepository transactionRepository,
            TransactionAccountEntryRepository entryRepository,
            AccountRepository accountRepository,
            CategoryRepository categoryRepository,
            CategoryGroupRepository categoryGroupRepository,
            HouseholdMemberRepository householdMemberRepository,
            HouseholdMemberResolver householdMemberResolver
    ) {
        this.transactionRepository = transactionRepository;
        this.entryRepository = entryRepository;
        this.accountRepository = accountRepository;
        this.categoryRepository = categoryRepository;
        this.categoryGroupRepository = categoryGroupRepository;
        this.householdMemberRepository = householdMemberRepository;
        this.householdMemberResolver = householdMemberResolver;
    }

    @Transactional(readOnly = true)
    public StatisticsResponse find(
            CurrentHousehold currentHousehold,
            StatisticsFilter filter
    ) {
        validateFilter(currentHousehold, filter);
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        List<LedgerTransaction> currentTransactions = findRange(
                currentHousehold.householdId(), filter.from(), filter.to(), zoneId);
        List<LedgerTransaction> comparisonTransactions = filter.hasComparison()
                ? findRange(
                        currentHousehold.householdId(),
                        filter.compareFrom(),
                        filter.compareTo(),
                        zoneId
                )
                : List.of();
        LedgerContext context = loadContext(
                currentHousehold.householdId(),
                currentTransactions,
                comparisonTransactions
        );
        List<LedgerTransaction> scopedCurrent = applyScope(currentTransactions, filter);
        List<LedgerTransaction> scopedComparison = applyScope(comparisonTransactions, filter);
        Metric currentMetric = metric(scopedCurrent, filter.isAllScope(), context);
        Metric comparisonMetric = filter.hasComparison()
                ? metric(scopedComparison, filter.isAllScope(), context)
                : null;

        return new StatisticsResponse(
                new StatisticsResponse.Period(
                        filter.from(), filter.to(), currentHousehold.timezone()),
                currentMetric.toSummary(),
                comparison(filter, currentMetric, comparisonMetric),
                subjects(filter, scopedCurrent, context),
                categories(scopedCurrent, currentMetric.netSpendingAmount(), context),
                accounts(scopedCurrent, context),
                months(filter, scopedCurrent, zoneId, context)
        );
    }

    @Transactional(readOnly = true)
    public List<SavingsActivityResponse> findSavingsActivities(
            CurrentHousehold currentHousehold,
            LocalDate from,
            LocalDate to
    ) {
        validateRange(from, to);
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        List<LedgerTransaction> transactions = findRange(
                currentHousehold.householdId(), from, to, zoneId);
        LedgerContext context = loadContext(
                currentHousehold.householdId(), transactions, List.of());

        return transactions.stream()
                .filter(transaction -> transaction.getType() == TransactionType.TRANSFER)
                .map(transaction -> toSavingsActivity(transaction, zoneId, context))
                .filter(Objects::nonNull)
                .sorted(Comparator
                        .comparing(SavingsActivityResponse::occurredAt)
                        .reversed()
                        .thenComparing(SavingsActivityResponse::transactionId, Comparator.reverseOrder()))
                .toList();
    }

    private void validateFilter(
            CurrentHousehold currentHousehold,
            StatisticsFilter filter
    ) {
        RequestValidator validator = new RequestValidator()
                .required(filter.from(), "from")
                .required(filter.to(), "to");
        if (filter.from() != null && filter.to() != null) {
            validator.check(
                    !filter.from().isAfter(filter.to()),
                    "from",
                    "range",
                    "from은 to보다 늦을 수 없습니다."
            );
        }
        boolean comparisonPair = (filter.compareFrom() == null) == (filter.compareTo() == null);
        validator.check(
                comparisonPair,
                filter.compareFrom() == null ? "compareFrom" : "compareTo",
                "pair",
                "compareFrom과 compareTo는 함께 지정해야 합니다."
        );
        if (filter.compareFrom() != null && filter.compareTo() != null) {
            validator.check(
                    !filter.compareFrom().isAfter(filter.compareTo()),
                    "compareFrom",
                    "range",
                    "compareFrom은 compareTo보다 늦을 수 없습니다."
            );
        }
        validateScope(validator, filter.scope(), filter.ownerMemberId());
        validator.throwIfInvalid();

        if (filter.scope() == TransactionScope.PERSONAL) {
            householdMemberResolver.require(
                    currentHousehold.householdId(), filter.ownerMemberId());
        }
    }

    private void validateRange(LocalDate from, LocalDate to) {
        RequestValidator validator = new RequestValidator()
                .required(from, "from")
                .required(to, "to");
        if (from != null && to != null) {
            validator.check(
                    !from.isAfter(to),
                    "from",
                    "range",
                    "from은 to보다 늦을 수 없습니다."
            );
        }
        validator.throwIfInvalid();
    }

    private void validateScope(
            RequestValidator validator,
            TransactionScope scope,
            Long ownerMemberId
    ) {
        if (scope == null) {
            validator.check(
                    ownerMemberId == null,
                    "ownerMemberId",
                    "unexpected",
                    "scope 없이 ownerMemberId를 지정할 수 없습니다."
            );
        } else if (scope == TransactionScope.PERSONAL) {
            validator.required(ownerMemberId, "ownerMemberId");
        } else {
            validator.check(
                    ownerMemberId == null,
                    "ownerMemberId",
                    "unexpected",
                    "SHARED scope에는 ownerMemberId를 지정할 수 없습니다."
            );
        }
    }

    private List<LedgerTransaction> findRange(
            Long householdId,
            LocalDate from,
            LocalDate to,
            ZoneId zoneId
    ) {
        return transactionRepository
                .findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                        householdId,
                        from.atStartOfDay(zoneId).toInstant(),
                        to.plusDays(1).atStartOfDay(zoneId).toInstant()
                );
    }

    private LedgerContext loadContext(
            Long householdId,
            List<LedgerTransaction> currentTransactions,
            List<LedgerTransaction> comparisonTransactions
    ) {
        Set<Long> transactionIds = new LinkedHashSet<>();
        currentTransactions.forEach(transaction -> transactionIds.add(transaction.getId()));
        comparisonTransactions.forEach(transaction -> transactionIds.add(transaction.getId()));
        List<TransactionAccountEntry> entries = transactionIds.isEmpty()
                ? List.of()
                : entryRepository
                        .findAllByHouseholdIdAndTransactionIdInOrderByTransactionIdAscIdAsc(
                                householdId, transactionIds);
        Map<Long, List<TransactionAccountEntry>> entriesByTransaction = entries.stream()
                .collect(Collectors.groupingBy(
                        TransactionAccountEntry::getTransactionId,
                        LinkedHashMap::new,
                        Collectors.toList()
                ));
        List<HouseholdMember> members = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(householdId);
        List<CategoryGroup> groups = categoryGroupRepository
                .findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(householdId);
        return new LedgerContext(
                entriesByTransaction,
                accountRepository.findAllByHouseholdIdOrderBySortOrderAscIdAsc(householdId)
                        .stream()
                        .collect(Collectors.toMap(Account::getId, Function.identity())),
                categoryRepository.findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(householdId)
                        .stream()
                        .collect(Collectors.toMap(Category::getId, Function.identity())),
                groups.stream().collect(Collectors.toMap(
                        CategoryGroup::getId,
                        CategoryGroup::isArchived
                )),
                members,
                members.stream().collect(Collectors.toMap(
                        HouseholdMember::getId,
                        Function.identity()
                ))
        );
    }

    private List<LedgerTransaction> applyScope(
            List<LedgerTransaction> transactions,
            StatisticsFilter filter
    ) {
        if (filter.scope() == null) {
            return transactions;
        }
        return transactions.stream()
                .filter(transaction -> filter.scope() == TransactionScope.SHARED
                        ? transaction.getScope() == TransactionScope.SHARED
                        : transaction.getScope() == TransactionScope.PERSONAL
                        && Objects.equals(
                                transaction.getOwnerMemberId(), filter.ownerMemberId()))
                .toList();
    }

    private Metric metric(
            List<LedgerTransaction> transactions,
            boolean savingsAvailable,
            LedgerContext context
    ) {
        MetricAccumulator accumulator = new MetricAccumulator(savingsAvailable);
        transactions.forEach(transaction -> accumulator.add(transaction, context));
        return accumulator.toMetric();
    }

    private StatisticsResponse.Comparison comparison(
            StatisticsFilter filter,
            Metric current,
            Metric previous
    ) {
        if (previous == null) {
            return null;
        }
        Long savingsDifference = current.savingsAmount() == null
                ? null
                : Math.subtractExact(current.savingsAmount(), previous.savingsAmount());
        BigDecimal savingsRateDifference = current.savingsRate() == null
                || previous.savingsRate() == null
                ? null
                : current.savingsRate().subtract(previous.savingsRate()).setScale(1);
        return new StatisticsResponse.Comparison(
                filter.compareFrom(),
                filter.compareTo(),
                previous.incomeAmount(),
                previous.netSpendingAmount(),
                previous.savingsAmount(),
                previous.savingsRate(),
                Math.subtractExact(current.incomeAmount(), previous.incomeAmount()),
                Math.subtractExact(
                        current.netSpendingAmount(), previous.netSpendingAmount()),
                savingsDifference,
                percentChange(current.incomeAmount(), previous.incomeAmount()),
                percentChange(
                        current.netSpendingAmount(), previous.netSpendingAmount()),
                current.savingsAmount() == null
                        ? null
                        : percentChange(current.savingsAmount(), previous.savingsAmount()),
                savingsRateDifference
        );
    }

    private List<StatisticsResponse.Subject> subjects(
            StatisticsFilter filter,
            List<LedgerTransaction> transactions,
            LedgerContext context
    ) {
        if (filter.scope() == TransactionScope.PERSONAL) {
            HouseholdMember member = context.membersById().get(filter.ownerMemberId());
            return List.of(new StatisticsResponse.Subject(
                    TransactionScope.PERSONAL,
                    toMember(member),
                    netSpending(transactions)
            ));
        }
        if (filter.scope() == TransactionScope.SHARED) {
            return List.of(new StatisticsResponse.Subject(
                    TransactionScope.SHARED,
                    null,
                    netSpending(transactions)
            ));
        }

        Map<Long, Long> personalAmounts = new LinkedHashMap<>();
        context.members().forEach(member -> personalAmounts.put(member.getId(), 0L));
        long sharedAmount = 0;
        for (LedgerTransaction transaction : transactions) {
            if (transaction.getType() != TransactionType.EXPENSE) {
                continue;
            }
            long amount = NetSpendingCalculator.amountOf(transaction);
            if (transaction.getScope() == TransactionScope.SHARED) {
                sharedAmount = Math.addExact(sharedAmount, amount);
            } else if (transaction.getScope() == TransactionScope.PERSONAL) {
                Long ownerId = transaction.getOwnerMemberId();
                if (!personalAmounts.containsKey(ownerId)) {
                    throw invalidLedger();
                }
                personalAmounts.put(
                        ownerId,
                        Math.addExact(personalAmounts.get(ownerId), amount)
                );
            }
        }
        List<StatisticsResponse.Subject> result = new ArrayList<>();
        context.members().forEach(member -> result.add(new StatisticsResponse.Subject(
                TransactionScope.PERSONAL,
                toMember(member),
                personalAmounts.get(member.getId())
        )));
        result.add(new StatisticsResponse.Subject(
                TransactionScope.SHARED,
                null,
                sharedAmount
        ));
        return result;
    }

    private List<StatisticsResponse.CategoryBreakdown> categories(
            List<LedgerTransaction> transactions,
            long totalNetSpending,
            LedgerContext context
    ) {
        Map<Long, Long> amounts = new LinkedHashMap<>();
        for (LedgerTransaction transaction : transactions) {
            if (transaction.getType() != TransactionType.EXPENSE) {
                continue;
            }
            amounts.merge(
                    transaction.getCategoryId(),
                    NetSpendingCalculator.amountOf(transaction),
                    Math::addExact
            );
        }
        return amounts.entrySet().stream()
                .filter(entry -> entry.getValue() != 0)
                .map(entry -> {
                    Category category = require(context.categoriesById(), entry.getKey());
                    boolean groupArchived = category.getGroupId() != null
                            && Boolean.TRUE.equals(
                                    context.archivedCategoryGroups().get(category.getGroupId()));
                    return new StatisticsResponse.CategoryBreakdown(
                            new StatisticsResponse.CategoryReference(
                                    category.getId(),
                                    category.getName(),
                                    category.isArchived() || groupArchived
                            ),
                            entry.getValue(),
                            totalNetSpending > 0
                                    ? percentage(entry.getValue(), totalNetSpending)
                                    : null
                    );
                })
                .sorted(Comparator
                        .comparingLong(StatisticsResponse.CategoryBreakdown::netSpendingAmount)
                        .reversed()
                        .thenComparing(item -> item.category().name())
                        .thenComparing(item -> item.category().id()))
                .toList();
    }

    private List<StatisticsResponse.AccountBreakdown> accounts(
            List<LedgerTransaction> transactions,
            LedgerContext context
    ) {
        Map<Long, Long> amounts = new LinkedHashMap<>();
        for (LedgerTransaction transaction : transactions) {
            if (transaction.getType() != TransactionType.EXPENSE) {
                continue;
            }
            TransactionAccountEntry primary = requireEntry(
                    transaction, EntryRole.PRIMARY, context);
            amounts.merge(
                    primary.getAccountId(),
                    NetSpendingCalculator.amountOf(transaction),
                    Math::addExact
            );
        }
        return amounts.entrySet().stream()
                .filter(entry -> entry.getValue() != 0)
                .map(entry -> {
                    Account account = require(context.accountsById(), entry.getKey());
                    return new StatisticsResponse.AccountBreakdown(
                            new StatisticsResponse.AccountReference(
                                    account.getId(),
                                    account.getName(),
                                    account.getType(),
                                    account.getNature(),
                                    account.isArchived()
                            ),
                            entry.getValue()
                    );
                })
                .sorted(Comparator
                        .comparingLong(StatisticsResponse.AccountBreakdown::netSpendingAmount)
                        .reversed()
                        .thenComparing(item -> item.account().name())
                        .thenComparing(item -> item.account().id()))
                .toList();
    }

    private List<StatisticsResponse.MonthTrend> months(
            StatisticsFilter filter,
            List<LedgerTransaction> transactions,
            ZoneId zoneId,
            LedgerContext context
    ) {
        Map<YearMonth, MetricAccumulator> months = new LinkedHashMap<>();
        YearMonth cursor = YearMonth.from(filter.from());
        YearMonth end = YearMonth.from(filter.to());
        while (!cursor.isAfter(end)) {
            months.put(cursor, new MetricAccumulator(filter.isAllScope()));
            cursor = cursor.plusMonths(1);
        }
        for (LedgerTransaction transaction : transactions) {
            YearMonth month = YearMonth.from(
                    transaction.getOccurredAt().atZone(zoneId).toLocalDate());
            MetricAccumulator accumulator = months.get(month);
            if (accumulator != null) {
                accumulator.add(transaction, context);
            }
        }
        return months.entrySet().stream()
                .map(entry -> {
                    Metric metric = entry.getValue().toMetric();
                    return new StatisticsResponse.MonthTrend(
                            entry.getKey(),
                            metric.incomeAmount(),
                            metric.netSpendingAmount(),
                            metric.savingsAmount(),
                            metric.savingsRate()
                    );
                })
                .toList();
    }

    private long netSpending(List<LedgerTransaction> transactions) {
        long amount = 0;
        for (LedgerTransaction transaction : transactions) {
            amount = Math.addExact(amount, NetSpendingCalculator.amountOf(transaction));
        }
        return amount;
    }

    private SavingsActivityResponse toSavingsActivity(
            LedgerTransaction transaction,
            ZoneId zoneId,
            LedgerContext context
    ) {
        long impact = savingsImpact(transaction, context);
        if (impact == 0) {
            return null;
        }
        TransactionAccountEntry sourceEntry = requireEntry(
                transaction, EntryRole.SOURCE, context);
        TransactionAccountEntry destinationEntry = requireEntry(
                transaction, EntryRole.DESTINATION, context);
        Account source = require(context.accountsById(), sourceEntry.getAccountId());
        Account destination = require(
                context.accountsById(), destinationEntry.getAccountId());
        return new SavingsActivityResponse(
                transaction.getId(),
                transaction.getOccurredAt().atZone(zoneId).toOffsetDateTime(),
                transaction.getAmount(),
                impact,
                new SavingsActivityResponse.AccountReference(
                        source.getId(), source.getName()),
                new SavingsActivityResponse.AccountReference(
                        destination.getId(), destination.getName()),
                transaction.getMemo(),
                transaction.getGeneratedFromRecurringId(),
                transaction.getRecurrenceDate()
        );
    }

    private long savingsImpact(
            LedgerTransaction transaction,
            LedgerContext context
    ) {
        if (transaction.getType() != TransactionType.TRANSFER) {
            return 0;
        }
        TransactionAccountEntry sourceEntry = requireEntry(
                transaction, EntryRole.SOURCE, context);
        TransactionAccountEntry destinationEntry = requireEntry(
                transaction, EntryRole.DESTINATION, context);
        Account source = require(context.accountsById(), sourceEntry.getAccountId());
        Account destination = require(
                context.accountsById(), destinationEntry.getAccountId());
        if (source.isSavingsEnabled() == destination.isSavingsEnabled()) {
            return 0;
        }
        if (!source.isSavingsEnabled()
                && source.getNature() == AccountNature.ASSET
                && destination.isSavingsEnabled()) {
            return transaction.getAmount();
        }
        if (source.isSavingsEnabled() && !destination.isSavingsEnabled()) {
            return Math.negateExact(transaction.getAmount());
        }
        return 0;
    }

    private TransactionAccountEntry requireEntry(
            LedgerTransaction transaction,
            EntryRole role,
            LedgerContext context
    ) {
        List<TransactionAccountEntry> entries = context.entriesByTransaction()
                .getOrDefault(transaction.getId(), List.of());
        List<TransactionAccountEntry> matching = entries.stream()
                .filter(entry -> entry.getEntryRole() == role)
                .toList();
        if (matching.size() != 1) {
            throw invalidLedger();
        }
        return matching.getFirst();
    }

    private <T> T require(Map<Long, T> values, Long id) {
        T value = values.get(id);
        if (value == null) {
            throw invalidLedger();
        }
        return value;
    }

    private ApiException invalidLedger() {
        return new ApiException(
                HttpStatus.CONFLICT,
                ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID
        );
    }

    private StatisticsResponse.Member toMember(HouseholdMember member) {
        return new StatisticsResponse.Member(
                member.getId(),
                member.getUser().getId(),
                member.getUser().getDisplayName()
        );
    }

    private static BigDecimal savingsRate(long savingsAmount, long incomeAmount) {
        if (incomeAmount == 0) {
            return null;
        }
        return percentage(savingsAmount, incomeAmount);
    }

    private static BigDecimal percentChange(long current, long previous) {
        if (previous == 0) {
            return null;
        }
        return percentage(Math.subtractExact(current, previous), previous);
    }

    private static BigDecimal percentage(long numerator, long denominator) {
        return BigDecimal.valueOf(numerator)
                .multiply(ONE_HUNDRED)
                .divide(BigDecimal.valueOf(denominator), 1, RoundingMode.HALF_UP);
    }

    private final class MetricAccumulator {

        private final boolean savingsAvailable;
        private long incomeAmount;
        private long netSpendingAmount;
        private long savingsAmount;

        private MetricAccumulator(boolean savingsAvailable) {
            this.savingsAvailable = savingsAvailable;
        }

        private void add(LedgerTransaction transaction, LedgerContext context) {
            if (transaction.getType() == TransactionType.INCOME
                    && transaction.getAdjustmentType() == AdjustmentType.NORMAL) {
                incomeAmount = Math.addExact(incomeAmount, transaction.getAmount());
            }
            netSpendingAmount = Math.addExact(
                    netSpendingAmount,
                    NetSpendingCalculator.amountOf(transaction)
            );
            if (savingsAvailable) {
                savingsAmount = Math.addExact(
                        savingsAmount,
                        savingsImpact(transaction, context)
                );
            }
        }

        private Metric toMetric() {
            Long savings = savingsAvailable ? savingsAmount : null;
            return new Metric(
                    incomeAmount,
                    netSpendingAmount,
                    savings,
                    savings == null ? null : savingsRate(savings, incomeAmount)
            );
        }
    }

    private record Metric(
            long incomeAmount,
            long netSpendingAmount,
            Long savingsAmount,
            BigDecimal savingsRate
    ) {

        private StatisticsResponse.Summary toSummary() {
            return new StatisticsResponse.Summary(
                    incomeAmount,
                    netSpendingAmount,
                    savingsAmount,
                    savingsRate
            );
        }
    }

    private record LedgerContext(
            Map<Long, List<TransactionAccountEntry>> entriesByTransaction,
            Map<Long, Account> accountsById,
            Map<Long, Category> categoriesById,
            Map<Long, Boolean> archivedCategoryGroups,
            List<HouseholdMember> members,
            Map<Long, HouseholdMember> membersById
    ) {
    }
}
