package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.budget.BudgetMonthResponse;
import io.github.xxh3898.ourledger.budget.BudgetService;
import io.github.xxh3898.ourledger.calendar.CalendarMonthResponse;
import io.github.xxh3898.ourledger.calendar.CalendarService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupResponse;
import io.github.xxh3898.ourledger.category.CategoryGroupService;
import io.github.xxh3898.ourledger.category.CategoryGroupUpdateRequest;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryResponse;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.recurring.RecurrenceFrequency;
import io.github.xxh3898.ourledger.recurring.RecurringCreateRequest;
import io.github.xxh3898.ourledger.recurring.RecurringGenerationService;
import io.github.xxh3898.ourledger.recurring.RecurringOccurrenceProcessor;
import io.github.xxh3898.ourledger.recurring.RecurringStatus;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionResponse;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionService;
import io.github.xxh3898.ourledger.recurring.RecurringUpdateRequest;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.statistics.StatisticsFilter;
import io.github.xxh3898.ourledger.statistics.StatisticsResponse;
import io.github.xxh3898.ourledger.statistics.StatisticsService;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntry;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import io.github.xxh3898.ourledger.transaction.TransactionUpdateRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.YearMonth;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class RecurringIntegrationTest {

    private static final String OWNER_EMAIL = "recurring-owner@example.test";
    private static final Instant NOON_AUGUST_28 = Instant.parse("2026-08-28T03:00:00Z");
    private static final LocalDate AUGUST_28 = LocalDate.of(2026, 8, 28);

    @Autowired private HouseholdBootstrapService bootstrapService;
    @Autowired private UserRepository userRepository;
    @Autowired private HouseholdRepository householdRepository;
    @Autowired private HouseholdMemberRepository householdMemberRepository;
    @Autowired private AccountService accountService;
    @Autowired private CategoryService categoryService;
    @Autowired private CategoryGroupService categoryGroupService;
    @Autowired private CategoryRepository categoryRepository;
    @Autowired private RecurringTransactionService recurringService;
    @Autowired private RecurringGenerationService generationService;
    @Autowired private RecurringOccurrenceProcessor occurrenceProcessor;
    @Autowired private LedgerTransactionRepository transactionRepository;
    @Autowired private TransactionAccountEntryRepository entryRepository;
    @Autowired private TransactionService transactionService;
    @Autowired private CalendarService calendarService;
    @Autowired private BudgetService budgetService;
    @Autowired private StatisticsService statisticsService;
    @Autowired private JdbcTemplate jdbcTemplate;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        bootstrapService.provision(new HouseholdBootstrapRequest(
                "Recurring Household",
                OWNER_EMAIL,
                "Recurring Owner",
                "recurring-member@example.test",
                "Recurring Member"
        ));
        User owner = userRepository.findByEmail(OWNER_EMAIL).orElseThrow();
        Household household = householdRepository.findAll().getFirst();
        HouseholdMember ownerMember = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(household.getId())
                .stream()
                .filter(member -> member.getRole() == HouseholdRole.OWNER)
                .findFirst()
                .orElseThrow();
        ownerMemberId = ownerMember.getId();
        currentHousehold = new CurrentHousehold(
                owner.getId(), owner.getEmail(), owner.getDisplayName(), household.getId(),
                household.getName(), household.getBaseCurrency(), household.getTimezone(),
                HouseholdRole.OWNER
        );
    }

    @AfterEach
    void clearDatabaseAfterTest() {
        clearDatabase();
    }

    @Test
    void should_generateCanonicalEntriesAndMetrics_when_allSupportedTemplatesAreDue() {
        AccountResponse checking = createAccount(
                "주거래 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        AccountResponse savings = createAccount(
                "저축 통장", AccountType.SAVINGS, AccountNature.ASSET, 0, true);
        AccountResponse card = createAccount(
                "생활 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY, 0, false);
        Category income = createCategory(CategoryType.INCOME, "급여");
        Category expense = createCategory(CategoryType.EXPENSE, "생활비");

        RecurringTransactionResponse incomeRule = recurringService.createAt(
                currentHousehold,
                primaryRule("월급", TransactionType.INCOME, 3_000_000, income.getId(), checking.id()),
                NOON_AUGUST_28);
        RecurringTransactionResponse assetExpenseRule = recurringService.createAt(
                currentHousehold,
                primaryRule("현금 지출", TransactionType.EXPENSE, 10_000, expense.getId(), checking.id()),
                NOON_AUGUST_28);
        RecurringTransactionResponse cardExpenseRule = recurringService.createAt(
                currentHousehold,
                primaryRule("카드 지출", TransactionType.EXPENSE, 12_000, expense.getId(), card.id()),
                NOON_AUGUST_28);
        RecurringTransactionResponse savingsRule = recurringService.createAt(
                currentHousehold,
                transferRule("저축 이체", 20_000, checking.id(), savings.id()),
                NOON_AUGUST_28);
        RecurringTransactionResponse cardPaymentRule = recurringService.createAt(
                currentHousehold,
                transferRule("카드대금", 30_000, checking.id(), card.id()),
                NOON_AUGUST_28);

        assertThat(generationService.generateDue(NOON_AUGUST_28, 20)).isEqualTo(5);

        assertEntry(incomeRule.id(), EntryRole.PRIMARY, 3_000_000);
        assertEntry(assetExpenseRule.id(), EntryRole.PRIMARY, -10_000);
        assertEntry(cardExpenseRule.id(), EntryRole.PRIMARY, 12_000);
        assertEntries(savingsRule.id(), -20_000, 20_000);
        assertEntries(cardPaymentRule.id(), -30_000, -30_000);
        assertThat(transactionRepository.findAll())
                .allSatisfy(transaction -> {
                    assertThat(transaction.getCreatedBy()).isEqualTo(ownerMemberId);
                    assertThat(transaction.getUpdatedBy()).isEqualTo(ownerMemberId);
                    assertThat(transaction.getRecurrenceDate()).isEqualTo(AUGUST_28);
                    assertThat(transaction.getOccurredAt())
                            .isEqualTo(Instant.parse("2026-08-28T00:00:00Z"));
                });

        CalendarMonthResponse calendar = calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), null, null);
        BudgetMonthResponse budget = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));
        StatisticsResponse statistics = statisticsService.find(
                currentHousehold,
                new StatisticsFilter(
                        AUGUST_28.withDayOfMonth(1), AUGUST_28.withDayOfMonth(31),
                        null, null, null, null));

        assertThat(calendar.summary().netSpendingAmount()).isEqualTo(22_000);
        assertThat(calendar.days()).singleElement()
                .extracting(CalendarMonthResponse.Day::transactionCount)
                .isEqualTo(5L);
        assertThat(budget.scopes().getFirst().spentAmount()).isEqualTo(22_000);
        assertThat(statistics.summary().incomeAmount()).isEqualTo(3_000_000);
        assertThat(statistics.summary().netSpendingAmount()).isEqualTo(22_000);
        assertThat(statistics.summary().savingsAmount()).isEqualTo(20_000);
        assertThat(balance(checking.id())).isEqualTo(2_940_000);
        assertThat(balance(savings.id())).isEqualTo(20_000);
        assertThat(balance(card.id())).isEqualTo(-18_000);
        assertThat(recurringService.findAll(currentHousehold))
                .allMatch(item -> item.status() == RecurringStatus.ENDED);
    }

    @Test
    void should_catchUpOnceAndNeverRecreateDeletedOccurrence_when_serverWasDown() {
        AccountResponse checking = createAccount(
                "생활비", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        Category expense = createCategory(CategoryType.EXPENSE, "구독");
        RecurringTransactionResponse rule = recurringService.createAt(
                currentHousehold,
                recurringRequest(
                        "매일 구독", TransactionType.EXPENSE, 1_000, expense.getId(),
                        checking.id(), null, null, RecurrenceFrequency.DAILY, 1,
                        AUGUST_28, null, true),
                NOON_AUGUST_28
        );
        Instant august30Noon = Instant.parse("2026-08-30T03:00:00Z");

        assertThat(generationService.generateDue(august30Noon, 2)).isEqualTo(2);
        assertThat(generatedFor(rule.id())).hasSize(2);
        assertThat(generationService.generateDue(august30Noon, 10)).isEqualTo(1);
        assertThat(generationService.generateDue(august30Noon, 10)).isZero();
        List<LedgerTransaction> generated = generatedFor(rule.id());
        assertThat(generated).extracting(LedgerTransaction::getRecurrenceDate)
                .containsExactlyInAnyOrder(
                        LocalDate.of(2026, 8, 28),
                        LocalDate.of(2026, 8, 29),
                        LocalDate.of(2026, 8, 30));

        LedgerTransaction deletedOccurrence = generated.stream()
                .filter(item -> item.getRecurrenceDate().equals(LocalDate.of(2026, 8, 29)))
                .findFirst().orElseThrow();
        transactionService.delete(
                currentHousehold, deletedOccurrence.getId(), deletedOccurrence.getVersion());

        assertThat(generationService.generateDue(august30Noon, 10)).isZero();
        assertThat(transactionRepository.count()).isEqualTo(3);
        assertThat(transactionRepository.existsByGeneratedFromRecurringIdAndRecurrenceDate(
                rule.id(), LocalDate.of(2026, 8, 29))).isTrue();
    }

    @Test
    void should_applyFutureTemplateOnlyAndSkipPausedPeriod_when_ruleIsEditedAndResumed() {
        AccountResponse checking = createAccount(
                "자동이체 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        Category expense = createCategory(CategoryType.EXPENSE, "보험");
        RecurringCreateRequest createRequest = recurringRequest(
                "보험료", TransactionType.EXPENSE, 10_000, expense.getId(), checking.id(),
                null, null, RecurrenceFrequency.DAILY, 1, AUGUST_28, null, true);
        RecurringTransactionResponse created = recurringService.createAt(
                currentHousehold, createRequest, NOON_AUGUST_28);
        RecurringTransactionResponse paused = recurringService.updateAt(
                currentHousehold, created.id(), updateFrom(created, 10_000, false),
                NOON_AUGUST_28);

        assertThat(generationService.generateDue(NOON_AUGUST_28, 10)).isZero();
        RecurringTransactionResponse resumed = recurringService.updateAt(
                currentHousehold, paused.id(), updateFrom(paused, 10_000, true),
                NOON_AUGUST_28);
        assertThat(resumed.nextRecurrenceDate()).isEqualTo(LocalDate.of(2026, 8, 29));
        assertThat(generationService.generateDue(NOON_AUGUST_28, 10)).isZero();

        Instant august29Noon = Instant.parse("2026-08-29T03:00:00Z");
        assertThat(generationService.generateDue(august29Noon, 10)).isEqualTo(1);
        RecurringTransactionResponse edited = recurringService.updateAt(
                currentHousehold,
                resumed.id(),
                updateFrom(recurringService.findAll(currentHousehold).getFirst(), 20_000, true),
                august29Noon
        );
        Instant august30Noon = Instant.parse("2026-08-30T03:00:00Z");
        assertThat(generationService.generateDue(august30Noon, 10)).isEqualTo(1);

        assertThat(generatedFor(created.id()))
                .extracting(LedgerTransaction::getAmount)
                .containsExactlyInAnyOrder(10_000L, 20_000L);
        LedgerTransaction first = generatedFor(created.id()).stream()
                .filter(item -> item.getAmount() == 10_000)
                .findFirst().orElseThrow();
        TransactionResponse changed = transactionService.update(
                currentHousehold,
                first.getId(),
                new TransactionUpdateRequest(
                        first.getVersion(), TransactionType.EXPENSE, 15_000L,
                        TransactionScope.PERSONAL, ownerMemberId, ownerMemberId,
                        expense.getId(), checking.id(), null, null,
                        first.getOccurredAt(), "수동 보정", AdjustmentType.NORMAL, null
                )
        );
        assertThat(changed.generatedFromRecurringId()).isEqualTo(created.id());
        assertThat(recurringService.findAll(currentHousehold).getFirst().amount())
                .isEqualTo(edited.amount());

        assertApiError(
                ApiErrorCode.RECURRING_VERSION_CONFLICT,
                () -> recurringService.updateAt(
                        currentHousehold, created.id(), updateFrom(created, 99_000, true),
                        august30Noon)
        );
    }

    @Test
    void should_protectOnlyActiveFutureReferences_when_referenceLifecycleChanges() {
        CategoryGroupResponse group = categoryGroupService.create(
                currentHousehold,
                new CategoryGroupCreateRequest("고정비", CategoryType.EXPENSE, 0));
        CategoryResponse categoryResponse = categoryService.create(
                currentHousehold,
                new CategoryCreateRequest(
                        group.id(), "보험", CategoryType.EXPENSE, null, null, 0));
        Category category = categoryRepository.findById(categoryResponse.id()).orElseThrow();
        AccountResponse checking = createAccount(
                "고정비 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        RecurringTransactionResponse active = recurringService.createAt(
                currentHousehold,
                primaryRule("보험료", TransactionType.EXPENSE, 10_000, category.getId(), checking.id()),
                NOON_AUGUST_28);

        assertApiError(
                ApiErrorCode.RECURRING_REFERENCE_IN_USE,
                () -> accountService.update(
                        currentHousehold, checking.id(), accountUpdate(checking, true)));
        assertApiError(
                ApiErrorCode.RECURRING_REFERENCE_IN_USE,
                () -> categoryService.update(
                        currentHousehold,
                        category.getId(),
                        new io.github.xxh3898.ourledger.category.CategoryUpdateRequest(
                                group.id(), category.getName(), null, null, 0, true)));
        assertApiError(
                ApiErrorCode.RECURRING_REFERENCE_IN_USE,
                () -> categoryGroupService.update(
                        currentHousehold,
                        group.id(),
                        new CategoryGroupUpdateRequest(group.name(), group.sortOrder(), true)));

        RecurringTransactionResponse paused = recurringService.updateAt(
                currentHousehold, active.id(), updateFrom(active, active.amount(), false),
                NOON_AUGUST_28);
        AccountResponse archived = accountService.update(
                currentHousehold, checking.id(), accountUpdate(checking, true));
        CategoryResponse archivedCategory = categoryService.update(
                currentHousehold,
                category.getId(),
                new io.github.xxh3898.ourledger.category.CategoryUpdateRequest(
                        group.id(), category.getName(), null, null, 0, true));
        CategoryGroupResponse archivedGroup = categoryGroupService.update(
                currentHousehold,
                group.id(),
                new CategoryGroupUpdateRequest(group.name(), group.sortOrder(), true));
        assertThat(archived.archived()).isTrue();
        assertThat(archivedCategory.archived()).isTrue();
        assertThat(archivedGroup.archived()).isTrue();
        assertApiError(
                ApiErrorCode.ARCHIVED_CATEGORY_NOT_ALLOWED,
                () -> recurringService.updateAt(
                        currentHousehold,
                        paused.id(),
                        updateFrom(paused, paused.amount(), true),
                        NOON_AUGUST_28)
        );
    }

    @Test
    void should_createExactlyOneOccurrence_when_twoWorkersRace() throws Exception {
        AccountResponse checking = createAccount(
                "경합 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        Category expense = createCategory(CategoryType.EXPENSE, "경합 구독");
        RecurringTransactionResponse rule = recurringService.createAt(
                currentHousehold,
                primaryRule("경합 규칙", TransactionType.EXPENSE, 5_000, expense.getId(), checking.id()),
                NOON_AUGUST_28);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<RecurringOccurrenceProcessor.Result> first = executor.submit(() -> {
                ready.countDown();
                start.await();
                return occurrenceProcessor.generateOne(rule.id(), NOON_AUGUST_28);
            });
            Future<RecurringOccurrenceProcessor.Result> second = executor.submit(() -> {
                ready.countDown();
                start.await();
                return occurrenceProcessor.generateOne(rule.id(), NOON_AUGUST_28);
            });
            ready.await();
            start.countDown();

            assertThat(List.of(first.get(), second.get()))
                    .containsExactlyInAnyOrder(
                            RecurringOccurrenceProcessor.Result.GENERATED,
                            RecurringOccurrenceProcessor.Result.NOT_DUE);
        } finally {
            executor.shutdownNow();
        }
        assertThat(generatedFor(rule.id())).hasSize(1);
        assertThat(entryRepository.count()).isEqualTo(1);
    }

    @Test
    void should_commitHealthyRule_when_anotherDueRuleFails() {
        AccountResponse checking = createAccount(
                "격리 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        Category expense = createCategory(CategoryType.EXPENSE, "격리 구독");
        RecurringTransactionResponse broken = recurringService.createAt(
                currentHousehold,
                primaryRule("깨진 규칙", TransactionType.EXPENSE, 1_000, expense.getId(), checking.id()),
                NOON_AUGUST_28);
        RecurringTransactionResponse healthy = recurringService.createAt(
                currentHousehold,
                primaryRule("정상 규칙", TransactionType.EXPENSE, 2_000, expense.getId(), checking.id()),
                NOON_AUGUST_28);
        jdbcTemplate.update(
                "DELETE FROM recurring_transaction_accounts WHERE recurring_transaction_id = ?",
                broken.id());

        assertThat(generationService.generateDue(NOON_AUGUST_28, 10)).isEqualTo(1);
        assertThat(generatedFor(broken.id())).isEmpty();
        assertThat(generatedFor(healthy.id())).singleElement()
                .extracting(LedgerTransaction::getAmount)
                .isEqualTo(2_000L);
    }

    @Test
    void should_rejectUnsupportedOrForeignTemplate_when_ruleIsCreated() {
        AccountResponse checking = createAccount(
                "검증 통장", AccountType.CHECKING, AccountNature.ASSET, 0, false);
        Category expense = createCategory(CategoryType.EXPENSE, "검증 지출");

        RecurringCreateRequest autoPostFalse = new RecurringCreateRequest(
                "수동 승인", TransactionType.EXPENSE, 1_000L,
                TransactionScope.PERSONAL, ownerMemberId, ownerMemberId, expense.getId(),
                checking.id(), null, null, RecurrenceFrequency.MONTHLY, 1,
                AUGUST_28, null, LocalTime.of(9, 0), null, false, true);
        assertApiError(
                ApiErrorCode.RECURRING_AUTO_POST_REQUIRED,
                () -> recurringService.createAt(
                        currentHousehold, autoPostFalse, NOON_AUGUST_28));

        RecurringCreateRequest recurringRefundShape = new RecurringCreateRequest(
                "잘못된 시작일", TransactionType.EXPENSE, 1_000L,
                TransactionScope.PERSONAL, ownerMemberId, ownerMemberId, expense.getId(),
                checking.id(), null, null, RecurrenceFrequency.MONTHLY, 1,
                AUGUST_28.minusDays(1), null, LocalTime.of(9, 0), null, true, true);
        assertApiError(
                ApiErrorCode.INVALID_REQUEST,
                () -> recurringService.createAt(
                        currentHousehold, recurringRefundShape, NOON_AUGUST_28));

        CurrentHousehold foreign = createForeignHousehold();
        AccountResponse foreignAccount = accountService.create(
                foreign,
                new AccountCreateRequest(
                        "외부 통장", null, AccountType.CHECKING, AccountNature.ASSET,
                        AccountOwnership.SHARED, null, 0L, AUGUST_28, "KRW", null,
                        false, 0));
        RecurringCreateRequest foreignReference = recurringRequest(
                "외부 참조", TransactionType.EXPENSE, 1_000, expense.getId(),
                foreignAccount.id(), null, null, RecurrenceFrequency.DAILY, 1,
                AUGUST_28, null, true);
        assertApiError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                () -> recurringService.createAt(
                        currentHousehold, foreignReference, NOON_AUGUST_28));
    }

    private RecurringCreateRequest primaryRule(
            String name,
            TransactionType type,
            long amount,
            Long categoryId,
            Long accountId
    ) {
        return recurringRequest(
                name, type, amount, categoryId, accountId, null, null,
                RecurrenceFrequency.DAILY, 1, AUGUST_28, AUGUST_28, true);
    }

    private RecurringCreateRequest transferRule(
            String name,
            long amount,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        return recurringRequest(
                name, TransactionType.TRANSFER, amount, null, null,
                sourceAccountId, destinationAccountId, RecurrenceFrequency.DAILY, 1,
                AUGUST_28, AUGUST_28, true);
    }

    private RecurringCreateRequest recurringRequest(
            String name,
            TransactionType type,
            long amount,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            boolean active
    ) {
        boolean transfer = type == TransactionType.TRANSFER;
        return new RecurringCreateRequest(
                name,
                type,
                amount,
                transfer ? null : TransactionScope.PERSONAL,
                transfer ? null : ownerMemberId,
                type == TransactionType.EXPENSE ? ownerMemberId : null,
                categoryId,
                accountId,
                sourceAccountId,
                destinationAccountId,
                frequency,
                intervalValue,
                startDate,
                endDate,
                LocalTime.of(9, 0),
                null,
                true,
                active
        );
    }

    private RecurringUpdateRequest updateFrom(
            RecurringTransactionResponse recurring,
            long amount,
            boolean active
    ) {
        Long primary = account(recurring, EntryRole.PRIMARY);
        Long source = account(recurring, EntryRole.SOURCE);
        Long destination = account(recurring, EntryRole.DESTINATION);
        return new RecurringUpdateRequest(
                recurring.version(), recurring.name(), recurring.type(), amount,
                recurring.scope(), recurring.owner() == null ? null : recurring.owner().memberId(),
                recurring.payer() == null ? null : recurring.payer().memberId(),
                recurring.category() == null ? null : recurring.category().id(),
                primary, source, destination, recurring.frequency(), recurring.intervalValue(),
                recurring.startDate(), recurring.endDate(), recurring.scheduledLocalTime(),
                recurring.memo(), true, active
        );
    }

    private Long account(RecurringTransactionResponse recurring, EntryRole role) {
        return recurring.accounts().stream()
                .filter(item -> item.role() == role)
                .map(item -> item.account().id())
                .findFirst()
                .orElse(null);
    }

    private AccountResponse createAccount(
            String name,
            AccountType type,
            AccountNature nature,
            long openingBalance,
            boolean savingsEnabled
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name, null, type, nature, AccountOwnership.PERSONAL, ownerMemberId,
                openingBalance, AUGUST_28.withDayOfMonth(1), "KRW", null,
                savingsEnabled, (int) jdbcTemplate.queryForObject(
                        "SELECT COUNT(*) FROM accounts", Long.class).longValue()
        ));
    }

    private AccountUpdateRequest accountUpdate(AccountResponse account, boolean archived) {
        return new AccountUpdateRequest(
                account.name(), account.institution(), account.type(), account.nature(),
                account.ownership(), account.owner().memberId(), account.openingBalance(),
                account.openingBalanceAsOf(), account.currency(), account.lastFour(),
                account.savingsEnabled(), account.sortOrder(), archived
        );
    }

    private Category createCategory(CategoryType type, String name) {
        CategoryResponse response = categoryService.create(
                currentHousehold,
                new CategoryCreateRequest(null, name, type, null, null, 0));
        return categoryRepository.findById(response.id()).orElseThrow();
    }

    private CurrentHousehold createForeignHousehold() {
        User user = userRepository.saveAndFlush(User.create(
                "foreign-recurring@example.test", "Foreign"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Foreign Household"));
        HouseholdMember member = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.OWNER));
        return new CurrentHousehold(
                user.getId(), user.getEmail(), user.getDisplayName(), household.getId(),
                household.getName(), household.getBaseCurrency(), household.getTimezone(),
                member.getRole()
        );
    }

    private List<LedgerTransaction> generatedFor(Long recurringId) {
        return transactionRepository.findAll().stream()
                .filter(transaction -> recurringId.equals(
                        transaction.getGeneratedFromRecurringId()))
                .toList();
    }

    private void assertEntry(Long recurringId, EntryRole role, long delta) {
        LedgerTransaction transaction = generatedFor(recurringId).getFirst();
        assertThat(entryRepository.findAllByTransactionIdAndHouseholdId(
                transaction.getId(), transaction.getHouseholdId()))
                .singleElement()
                .extracting(TransactionAccountEntry::getEntryRole,
                        TransactionAccountEntry::getBalanceDelta)
                .containsExactly(role, delta);
    }

    private void assertEntries(Long recurringId, long sourceDelta, long destinationDelta) {
        LedgerTransaction transaction = generatedFor(recurringId).getFirst();
        assertThat(entryRepository.findAllByTransactionIdAndHouseholdId(
                transaction.getId(), transaction.getHouseholdId()))
                .extracting(TransactionAccountEntry::getEntryRole,
                        TransactionAccountEntry::getBalanceDelta)
                .containsExactlyInAnyOrder(
                        org.assertj.core.groups.Tuple.tuple(EntryRole.SOURCE, sourceDelta),
                        org.assertj.core.groups.Tuple.tuple(
                                EntryRole.DESTINATION, destinationDelta));
    }

    private long balance(Long accountId) {
        return accountService.findAll(currentHousehold, true).stream()
                .filter(account -> account.id().equals(accountId))
                .findFirst().orElseThrow().currentBalance();
    }

    private void assertApiError(ApiErrorCode code, Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo(code));
    }

    private void clearDatabase() {
        jdbcTemplate.execute("""
                TRUNCATE TABLE
                    recurring_transaction_accounts,
                    transaction_account_entries,
                    transactions,
                    recurring_transactions,
                    budgets,
                    categories,
                    category_groups,
                    accounts,
                    household_members,
                    households,
                    users
                RESTART IDENTITY CASCADE
                """);
    }
}
