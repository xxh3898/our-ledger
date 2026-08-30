package io.github.xxh3898.ourledger.goal;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountBalanceService;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntry;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class MarriageGoalService {

    private static final String MARRIAGE_UNIQUE = "ux_goals_household_marriage";
    private static final String ACCOUNT_ASSIGNMENT_UNIQUE = "uq_goal_accounts_account";
    private static final int TREND_MONTHS = 6;
    private static final int AVERAGE_MONTHS = 3;
    private static final int RECENT_ACTIVITY_LIMIT = 10;

    private final GoalRepository goalRepository;
    private final GoalAccountRepository goalAccountRepository;
    private final AccountRepository accountRepository;
    private final AccountService accountService;
    private final AccountBalanceService accountBalanceService;
    private final HouseholdMemberResolver householdMemberResolver;
    private final LedgerTransactionRepository transactionRepository;
    private final TransactionAccountEntryRepository entryRepository;
    private final Clock clock;

    public MarriageGoalService(
            GoalRepository goalRepository,
            GoalAccountRepository goalAccountRepository,
            AccountRepository accountRepository,
            AccountService accountService,
            AccountBalanceService accountBalanceService,
            HouseholdMemberResolver householdMemberResolver,
            LedgerTransactionRepository transactionRepository,
            TransactionAccountEntryRepository entryRepository,
            Clock clock
    ) {
        this.goalRepository = goalRepository;
        this.goalAccountRepository = goalAccountRepository;
        this.accountRepository = accountRepository;
        this.accountService = accountService;
        this.accountBalanceService = accountBalanceService;
        this.householdMemberResolver = householdMemberResolver;
        this.transactionRepository = transactionRepository;
        this.entryRepository = entryRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public MarriageGoalViewResponse find(CurrentHousehold currentHousehold) {
        return buildView(currentHousehold);
    }

    @Transactional
    public MarriageGoalViewResponse create(
            CurrentHousehold currentHousehold,
            MarriageGoalCreateRequest request
    ) {
        validateGoal(request.name(), request.targetAmount());
        if (goalRepository.existsByHouseholdIdAndType(
                currentHousehold.householdId(), GoalType.MARRIAGE)) {
            throw goalAlreadyExists();
        }
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        Goal goal = Goal.createMarriage(
                currentHousehold.householdId(),
                request.name(),
                request.targetAmount(),
                actor.getId(),
                clock.instant()
        );
        try {
            goalRepository.saveAndFlush(goal);
        } catch (DataIntegrityViolationException exception) {
            throw mapDataConflict(exception);
        }
        return buildView(currentHousehold);
    }

    @Transactional
    public MarriageGoalViewResponse update(
            CurrentHousehold currentHousehold,
            MarriageGoalUpdateRequest request
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        validateGoal(request.name(), request.targetAmount());
        Goal goal = requireMarriageGoal(currentHousehold.householdId());
        if (goal.getVersion() != request.version()) {
            throw versionConflict();
        }
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        goal.update(
                request.name(),
                request.targetAmount(),
                actor.getId(),
                clock.instant()
        );
        try {
            goalRepository.flush();
        } catch (ObjectOptimisticLockingFailureException exception) {
            throw versionConflict();
        }
        return buildView(currentHousehold);
    }

    @Transactional
    public MarriageGoalViewResponse linkAccount(
            CurrentHousehold currentHousehold,
            Long accountId
    ) {
        Goal goal = requireMarriageGoal(currentHousehold.householdId());
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);

        Account account = accountService.requireAccountForPosting(
                currentHousehold.householdId(), accountId);
        if (goalAccountRepository.findByIdAccountId(account.getId()).isPresent()) {
            throw accountAlreadyAssigned();
        }
        if (account.getNature() != AccountNature.ASSET
                || !account.isSavingsEnabled()
                || account.isArchived()) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.GOAL_ACCOUNT_NOT_ELIGIBLE
            );
        }

        long startingBalance = accountBalanceService.currentBalance(account);
        GoalAccount link = GoalAccount.link(
                goal.getId(),
                account.getId(),
                currentHousehold.householdId(),
                startingBalance,
                clock.instant(),
                actor.getId()
        );
        try {
            goalAccountRepository.saveAndFlush(link);
        } catch (DataIntegrityViolationException exception) {
            throw mapDataConflict(exception);
        }
        return buildView(currentHousehold);
    }

    @Transactional
    public void unlinkAccount(CurrentHousehold currentHousehold, Long accountId) {
        Goal goal = requireMarriageGoal(currentHousehold.householdId());
        Account account = accountService.requireAccountForPosting(
                currentHousehold.householdId(), accountId);
        GoalAccount link = goalAccountRepository
                .findByIdGoalIdAndIdAccountIdAndHouseholdId(
                        goal.getId(), account.getId(), currentHousehold.householdId())
                .orElseThrow(this::notFound);
        goalAccountRepository.delete(link);
        goalAccountRepository.flush();
    }

    private MarriageGoalViewResponse buildView(CurrentHousehold currentHousehold) {
        Long householdId = currentHousehold.householdId();
        List<Account> accounts = accountRepository
                .findAllByHouseholdIdOrderBySortOrderAscIdAsc(householdId);
        Map<Long, Account> accountsById = accounts.stream().collect(Collectors.toMap(
                Account::getId,
                Function.identity()
        ));
        List<GoalAccount> allAssignments = goalAccountRepository
                .findAllByHouseholdId(householdId);
        Set<Long> assignedAccountIds = allAssignments.stream()
                .map(GoalAccount::getAccountId)
                .collect(Collectors.toSet());
        List<MarriageGoalViewResponse.EligibleAccount> eligibleAccounts = accounts.stream()
                .filter(account -> account.getNature() == AccountNature.ASSET)
                .filter(Account::isSavingsEnabled)
                .filter(account -> !account.isArchived())
                .filter(account -> !assignedAccountIds.contains(account.getId()))
                .map(this::toEligibleAccount)
                .toList();

        Goal goal = goalRepository
                .findByHouseholdIdAndType(householdId, GoalType.MARRIAGE)
                .orElse(null);
        if (goal == null) {
            return new MarriageGoalViewResponse(null, eligibleAccounts);
        }

        List<GoalAccount> links = allAssignments.stream()
                .filter(link -> link.getGoalId().equals(goal.getId()))
                .sorted(Comparator
                        .comparing(GoalAccount::getLinkedAt)
                        .thenComparing(GoalAccount::getAccountId))
                .toList();
        Map<Long, GoalAccount> linksByAccountId = links.stream().collect(Collectors.toMap(
                GoalAccount::getAccountId,
                Function.identity()
        ));

        long currentAmount = 0;
        List<MarriageGoalViewResponse.LinkedAccount> linkedAccounts = new ArrayList<>();
        for (GoalAccount link : links) {
            Account account = requireAccount(accountsById, link.getAccountId());
            long currentBalance = accountBalanceService.currentBalance(account);
            currentAmount = Math.addExact(currentAmount, currentBalance);
            linkedAccounts.add(toLinkedAccount(account, link, currentBalance));
        }

        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        YearMonth currentMonth = YearMonth.now(clock.withZone(zoneId));
        LedgerContext ledger = loadLedgerContext(householdId, accountsById);
        List<TransferImpact> impacts = ledger.transactions().stream()
                .map(transaction -> toTransferImpact(transaction, linksByAccountId, ledger))
                .toList();
        LinkedHashMap<YearMonth, Long> trendAmounts = emptyTrend(currentMonth);
        for (TransferImpact impact : impacts) {
            YearMonth month = YearMonth.from(
                    impact.transaction().getOccurredAt().atZone(zoneId));
            if (trendAmounts.containsKey(month)) {
                trendAmounts.put(
                        month,
                        Math.addExact(trendAmounts.get(month), impact.amount())
                );
            }
        }
        List<MarriageGoalViewResponse.MonthlyTrend> monthlyTrend = trendAmounts.entrySet()
                .stream()
                .map(entry -> new MarriageGoalViewResponse.MonthlyTrend(
                        entry.getKey(), entry.getValue()))
                .toList();
        Long recentAverage = recentAverage(
                currentMonth,
                zoneId,
                links,
                trendAmounts
        );
        GoalProjectionCalculator.Projection projection = GoalProjectionCalculator.calculate(
                currentAmount,
                goal.getTargetAmount(),
                recentAverage,
                currentMonth
        );
        List<MarriageGoalViewResponse.SavingsActivity> activities = impacts.stream()
                .filter(impact -> impact.amount() != 0)
                .limit(RECENT_ACTIVITY_LIMIT)
                .map(this::toSavingsActivity)
                .toList();

        MarriageGoalViewResponse.MarriageGoal responseGoal =
                new MarriageGoalViewResponse.MarriageGoal(
                        goal.getId(),
                        goal.getType(),
                        goal.getName(),
                        goal.getTargetAmount(),
                        goal.getVersion(),
                        currentAmount,
                        projection.achievementRate(),
                        projection.remainingAmount(),
                        trendAmounts.get(currentMonth),
                        recentAverage,
                        projection.status(),
                        projection.expectedAchievementMonth(),
                        monthlyTrend,
                        linkedAccounts,
                        activities,
                        goal.getCreatedAt(),
                        goal.getUpdatedAt()
                );
        return new MarriageGoalViewResponse(responseGoal, eligibleAccounts);
    }

    private LedgerContext loadLedgerContext(
            Long householdId,
            Map<Long, Account> accountsById
    ) {
        List<LedgerTransaction> transactions = transactionRepository
                .findAllByHouseholdIdAndTypeAndDeletedAtIsNullOrderByOccurredAtDescIdDesc(
                        householdId, TransactionType.TRANSFER);
        Set<Long> transactionIds = transactions.stream()
                .map(LedgerTransaction::getId)
                .collect(Collectors.toCollection(LinkedHashSet::new));
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
        return new LedgerContext(transactions, entriesByTransaction, accountsById);
    }

    private TransferImpact toTransferImpact(
            LedgerTransaction transaction,
            Map<Long, GoalAccount> linksByAccountId,
            LedgerContext context
    ) {
        TransactionAccountEntry sourceEntry = requireEntry(
                transaction, EntryRole.SOURCE, context);
        TransactionAccountEntry destinationEntry = requireEntry(
                transaction, EntryRole.DESTINATION, context);
        Account source = requireAccount(context.accountsById(), sourceEntry.getAccountId());
        Account destination = requireAccount(
                context.accountsById(), destinationEntry.getAccountId());
        boolean sourceInGoal = linkWasEffective(
                linksByAccountId.get(source.getId()), transaction.getOccurredAt());
        boolean destinationInGoal = linkWasEffective(
                linksByAccountId.get(destination.getId()), transaction.getOccurredAt());
        long amount = 0;
        if (!sourceInGoal && destinationInGoal) {
            amount = transaction.getAmount();
        } else if (sourceInGoal && !destinationInGoal) {
            amount = Math.negateExact(transaction.getAmount());
        }
        return new TransferImpact(transaction, source, destination, amount);
    }

    private boolean linkWasEffective(GoalAccount link, Instant occurredAt) {
        return link != null && !occurredAt.isBefore(link.getLinkedAt());
    }

    private TransactionAccountEntry requireEntry(
            LedgerTransaction transaction,
            EntryRole role,
            LedgerContext context
    ) {
        List<TransactionAccountEntry> matching = context.entriesByTransaction()
                .getOrDefault(transaction.getId(), List.of())
                .stream()
                .filter(entry -> entry.getEntryRole() == role)
                .toList();
        if (matching.size() != 1) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID
            );
        }
        return matching.getFirst();
    }

    private LinkedHashMap<YearMonth, Long> emptyTrend(YearMonth currentMonth) {
        LinkedHashMap<YearMonth, Long> trend = new LinkedHashMap<>();
        YearMonth start = currentMonth.minusMonths(TREND_MONTHS - 1L);
        for (int index = 0; index < TREND_MONTHS; index++) {
            trend.put(start.plusMonths(index), 0L);
        }
        return trend;
    }

    private Long recentAverage(
            YearMonth currentMonth,
            ZoneId zoneId,
            List<GoalAccount> links,
            Map<YearMonth, Long> trendAmounts
    ) {
        long total = 0;
        for (int monthsAgo = AVERAGE_MONTHS; monthsAgo >= 1; monthsAgo--) {
            YearMonth month = currentMonth.minusMonths(monthsAgo);
            Instant monthEndExclusive = month.plusMonths(1)
                    .atDay(1)
                    .atStartOfDay(zoneId)
                    .toInstant();
            boolean hasSample = links.stream()
                    .anyMatch(link -> link.getLinkedAt().isBefore(monthEndExclusive));
            if (!hasSample) {
                return null;
            }
            total = Math.addExact(total, trendAmounts.get(month));
        }
        return Math.floorDiv(total, AVERAGE_MONTHS);
    }

    private MarriageGoalViewResponse.SavingsActivity toSavingsActivity(
            TransferImpact impact
    ) {
        LedgerTransaction transaction = impact.transaction();
        return new MarriageGoalViewResponse.SavingsActivity(
                transaction.getId(),
                transaction.getOccurredAt(),
                transaction.getAmount(),
                impact.amount(),
                new MarriageGoalViewResponse.AccountReference(
                        impact.source().getId(), impact.source().getName()),
                new MarriageGoalViewResponse.AccountReference(
                        impact.destination().getId(), impact.destination().getName()),
                transaction.getMemo(),
                transaction.getGeneratedFromRecurringId(),
                transaction.getRecurrenceDate()
        );
    }

    private MarriageGoalViewResponse.LinkedAccount toLinkedAccount(
            Account account,
            GoalAccount link,
            long currentBalance
    ) {
        return new MarriageGoalViewResponse.LinkedAccount(
                account.getId(),
                account.getName(),
                account.getOwnership(),
                owner(account),
                currentBalance,
                link.getStartingBalance(),
                link.getLinkedAt(),
                account.isArchived()
        );
    }

    private MarriageGoalViewResponse.EligibleAccount toEligibleAccount(Account account) {
        return new MarriageGoalViewResponse.EligibleAccount(
                account.getId(),
                account.getName(),
                account.getOwnership(),
                owner(account),
                accountBalanceService.currentBalance(account)
        );
    }

    private MarriageGoalViewResponse.Owner owner(Account account) {
        if (account.getOwnerMemberId() == null) {
            return null;
        }
        HouseholdMember member = householdMemberResolver.require(
                account.getHouseholdId(), account.getOwnerMemberId());
        return new MarriageGoalViewResponse.Owner(
                member.getId(), member.getUser().getDisplayName());
    }

    private Account requireAccount(Map<Long, Account> accountsById, Long accountId) {
        Account account = accountsById.get(accountId);
        if (account == null) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.RESOURCE_STATE_CONFLICT
            );
        }
        return account;
    }

    private Goal requireMarriageGoal(Long householdId) {
        return goalRepository.findByHouseholdIdAndType(householdId, GoalType.MARRIAGE)
                .orElseThrow(this::notFound);
    }

    private void validateGoal(String name, Long targetAmount) {
        RequestValidator validator = new RequestValidator()
                .requiredText(name, "name")
                .required(targetAmount, "targetAmount");
        if (name != null) {
            validator.check(
                    name.strip().length() <= 100,
                    "name",
                    "size",
                    "100자 이하여야 합니다."
            );
        }
        if (targetAmount != null) {
            validator.check(
                    targetAmount > 0,
                    "targetAmount",
                    "positive",
                    "0보다 커야 합니다."
            );
        }
        validator.throwIfInvalid();
    }

    private RuntimeException mapDataConflict(DataIntegrityViolationException exception) {
        Throwable current = exception;
        while (current != null) {
            String message = current.getMessage();
            if (message != null && message.contains(MARRIAGE_UNIQUE)) {
                return goalAlreadyExists();
            }
            if (message != null && message.contains(ACCOUNT_ASSIGNMENT_UNIQUE)) {
                return accountAlreadyAssigned();
            }
            current = current.getCause();
        }
        return exception;
    }

    private ApiException goalAlreadyExists() {
        return new ApiException(HttpStatus.CONFLICT, ApiErrorCode.GOAL_ALREADY_EXISTS);
    }

    private ApiException accountAlreadyAssigned() {
        return new ApiException(
                HttpStatus.CONFLICT,
                ApiErrorCode.GOAL_ACCOUNT_ALREADY_ASSIGNED
        );
    }

    private ApiException versionConflict() {
        return new ApiException(HttpStatus.CONFLICT, ApiErrorCode.GOAL_VERSION_CONFLICT);
    }

    private ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, ApiErrorCode.RESOURCE_NOT_FOUND);
    }

    private record LedgerContext(
            List<LedgerTransaction> transactions,
            Map<Long, List<TransactionAccountEntry>> entriesByTransaction,
            Map<Long, Account> accountsById
    ) {
    }

    private record TransferImpact(
            LedgerTransaction transaction,
            Account source,
            Account destination,
            long amount
    ) {
    }
}
