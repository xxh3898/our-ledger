package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.budget.BudgetCreateRequest;
import io.github.xxh3898.ourledger.budget.BudgetMonthResponse;
import io.github.xxh3898.ourledger.budget.BudgetRepository;
import io.github.xxh3898.ourledger.budget.BudgetScope;
import io.github.xxh3898.ourledger.budget.BudgetService;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.calendar.CalendarMonthResponse;
import io.github.xxh3898.ourledger.calendar.CalendarService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.category.CategoryUpdateRequest;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.RefundCreateRequest;
import io.github.xxh3898.ourledger.transaction.RefundSummaryResponse;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import io.github.xxh3898.ourledger.transaction.TransactionUpdateRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class RefundLedgerIntegrationTest {

    private static final String OWNER_EMAIL = "refund-owner@example.test";
    private static final Instant ORIGINAL_OCCURRED_AT =
            Instant.parse("2026-08-27T03:00:00Z");
    private static final Instant REFUND_OCCURRED_AT =
            Instant.parse("2026-08-28T03:00:00Z");

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdBootstrapService householdBootstrapService;

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private AccountService accountService;

    @Autowired
    private CategoryGroupRepository categoryGroupRepository;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private CategoryService categoryService;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private CalendarService calendarService;

    @Autowired
    private BudgetService budgetService;

    @Autowired
    private BudgetRepository budgetRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long partnerMemberId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Refund Household",
                OWNER_EMAIL,
                "Refund Owner",
                "refund-member@example.test",
                "Refund Member"
        ));
        User owner = userRepository.findByEmail(OWNER_EMAIL).orElseThrow();
        Household household = householdRepository.findAll().getFirst();
        List<HouseholdMember> members = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(household.getId());
        ownerMemberId = members
                .stream()
                .filter(member -> member.getRole() == HouseholdRole.OWNER)
                .findFirst()
                .orElseThrow()
                .getId();
        partnerMemberId = members
                .stream()
                .filter(member -> member.getRole() == HouseholdRole.MEMBER)
                .findFirst()
                .orElseThrow()
                .getId();
        currentHousehold = currentHousehold(owner, household);
    }

    @AfterEach
    void removeFixtures() {
        clearDatabase();
    }

    @Test
    void should_restoreAssetAndDerivedMetrics_when_partialRefundIsCreatedAndDeleted() {
        AccountResponse account = createAccount(
                "생활비 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        Category category = createCategory(CategoryType.EXPENSE, "식비");
        budgetService.create(currentHousehold, new BudgetCreateRequest(
                YearMonth.of(2026, 8),
                BudgetScope.PERSONAL,
                ownerMemberId,
                category.getId(),
                100_000L
        ));
        TransactionResponse original = createExpense(50_000, category.getId(), account.id());

        TransactionResponse refund = transactionService.createRefund(
                currentHousehold,
                original.id(),
                refundRequest(20_000, "부분 환불")
        );

        assertThat(refund.adjustmentType()).isEqualTo(AdjustmentType.REFUND);
        assertThat(refund.type()).isEqualTo(TransactionType.EXPENSE);
        assertThat(refund.scope()).isEqualTo(original.scope());
        assertThat(refund.owner()).isEqualTo(original.owner());
        assertThat(refund.payer()).isEqualTo(original.payer());
        assertThat(refund.category()).isEqualTo(original.category());
        assertThat(refund.entries()).singleElement().satisfies(entry -> {
            assertThat(entry.role()).isEqualTo(EntryRole.PRIMARY);
            assertThat(entry.account().id()).isEqualTo(account.id());
            assertThat(entry.balanceDelta()).isEqualTo(20_000);
        });
        assertThat(currentBalance(account.id())).isEqualTo(70_000);

        RefundSummaryResponse summary =
                transactionService.findRefunds(currentHousehold, original.id());
        assertThat(summary.originalAmount()).isEqualTo(50_000);
        assertThat(summary.refundedAmount()).isEqualTo(20_000);
        assertThat(summary.remainingRefundableAmount()).isEqualTo(30_000);
        assertThat(summary.refunds()).singleElement()
                .extracting(RefundSummaryResponse.Refund::id)
                .isEqualTo(refund.id());
        assertDerivedSpending(30_000, 2);
        assertThat(calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), null, null).days())
                .containsExactly(
                        new CalendarMonthResponse.Day(
                                LocalDate.of(2026, 8, 27), 1, 50_000),
                        new CalendarMonthResponse.Day(
                                LocalDate.of(2026, 8, 28), 1, -20_000)
                );

        assertApiError(
                ApiErrorCode.TRANSACTION_VERSION_CONFLICT,
                () -> transactionService.delete(
                        currentHousehold, refund.id(), refund.version() + 1)
        );
        transactionService.delete(currentHousehold, refund.id(), refund.version());

        RefundSummaryResponse restored =
                transactionService.findRefunds(currentHousehold, original.id());
        assertThat(restored.refundedAmount()).isZero();
        assertThat(restored.remainingRefundableAmount()).isEqualTo(50_000);
        assertThat(restored.refunds()).isEmpty();
        assertThat(currentBalance(account.id())).isEqualTo(50_000);
        assertDerivedSpending(50_000, 1);
        assertThat(calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), null, null).days())
                .containsExactly(new CalendarMonthResponse.Day(
                        LocalDate.of(2026, 8, 27), 1, 50_000));
    }

    @Test
    void should_restoreSharedAndCategoryBuckets_when_sharedRefundIsDeleted() {
        AccountResponse account = createSharedAccount(
                "공동 생활비 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        Category category = createCategory(CategoryType.EXPENSE, "공동 식비");
        budgetService.create(currentHousehold, new BudgetCreateRequest(
                YearMonth.of(2026, 8),
                BudgetScope.SHARED,
                null,
                category.getId(),
                100_000L
        ));
        TransactionResponse original = transactionService.create(
                currentHousehold,
                new TransactionCreateRequest(
                        TransactionType.EXPENSE,
                        40_000L,
                        TransactionScope.SHARED,
                        null,
                        partnerMemberId,
                        category.getId(),
                        account.id(),
                        null,
                        null,
                        ORIGINAL_OCCURRED_AT,
                        "공동 지출",
                        AdjustmentType.NORMAL,
                        null
                )
        );

        TransactionResponse refund = transactionService.createRefund(
                currentHousehold,
                original.id(),
                refundRequest(15_000, "공동 부분 환불")
        );

        assertThat(refund.scope()).isEqualTo(TransactionScope.SHARED);
        assertThat(refund.owner()).isNull();
        assertThat(refund.payer()).isEqualTo(original.payer());
        assertThat(refund.category()).isEqualTo(original.category());
        assertThat(refund.entries()).singleElement().satisfies(entry -> {
            assertThat(entry.account().id()).isEqualTo(account.id());
            assertThat(entry.balanceDelta()).isEqualTo(15_000);
        });
        assertThat(currentBalance(account.id())).isEqualTo(75_000);
        assertSharedSpending(25_000, 2);

        transactionService.delete(currentHousehold, refund.id(), refund.version());

        assertThat(currentBalance(account.id())).isEqualTo(60_000);
        assertSharedSpending(40_000, 1);
    }

    @Test
    void should_reverseCardLiabilityAndEnforceCap_when_multipleRefundsReachOriginalAmount() {
        AccountResponse card = createAccount(
                "생활 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY, 0);
        Category category = createCategory(CategoryType.EXPENSE, "생활비");
        TransactionResponse original = createExpense(50_000, category.getId(), card.id());

        TransactionResponse first = transactionService.createRefund(
                currentHousehold, original.id(), refundRequest(20_000, null));
        TransactionResponse second = transactionService.createRefund(
                currentHousehold, original.id(), refundRequest(30_000, "전액 환불 완료"));

        assertThat(first.entries()).singleElement()
                .extracting(TransactionResponse.Entry::balanceDelta)
                .isEqualTo(-20_000L);
        assertThat(second.entries()).singleElement()
                .extracting(TransactionResponse.Entry::balanceDelta)
                .isEqualTo(-30_000L);
        assertThat(currentBalance(card.id())).isZero();
        RefundSummaryResponse summary =
                transactionService.findRefunds(currentHousehold, original.id());
        assertThat(summary.refundedAmount()).isEqualTo(50_000);
        assertThat(summary.remainingRefundableAmount()).isZero();

        assertApiError(
                ApiErrorCode.TRANSACTION_REFUND_EXCEEDS_ORIGINAL,
                () -> transactionService.createRefund(
                        currentHousehold, original.id(), refundRequest(1, null))
        );
    }

    @Test
    @Timeout(30)
    void should_preventCumulativeOverRefund_when_postgresqlRequestsRace() throws Exception {
        AccountResponse account = createAccount(
                "동시성 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        Category category = createCategory(CategoryType.EXPENSE, "동시성 지출");
        TransactionResponse original = createExpense(100_000, category.getId(), account.id());
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Object> first = executor.submit(
                    () -> concurrentRefund(original.id(), ready, start));
            Future<Object> second = executor.submit(
                    () -> concurrentRefund(original.id(), ready, start));
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<Object> results = List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS)
            );
            assertThat(results).filteredOn(TransactionResponse.class::isInstance).hasSize(1);
            assertThat(results).filteredOn(result ->
                    result == ApiErrorCode.TRANSACTION_REFUND_EXCEEDS_ORIGINAL).hasSize(1);
        } finally {
            executor.shutdownNow();
        }

        RefundSummaryResponse summary =
                transactionService.findRefunds(currentHousehold, original.id());
        assertThat(summary.refundedAmount()).isEqualTo(70_000);
        assertThat(summary.remainingRefundableAmount()).isEqualTo(30_000);
        assertThat(summary.refunds()).hasSize(1);
    }

    @Test
    void should_failClosedForInvalidOriginalsAndAllowArchivedReferences_when_refundRequested() {
        AccountResponse account = createAccount(
                "검증 통장", AccountType.CHECKING, AccountNature.ASSET, 200_000);
        AccountResponse destination = createAccount(
                "검증 적금", AccountType.SAVINGS, AccountNature.ASSET, 0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "검증 지출");
        Category incomeCategory = createCategory(CategoryType.INCOME, "검증 수입");
        TransactionResponse income = transactionService.create(
                currentHousehold,
                primaryRequest(
                        TransactionType.INCOME,
                        10_000,
                        incomeCategory.getId(),
                        account.id()
                )
        );
        TransactionResponse transfer = transactionService.create(
                currentHousehold,
                transferRequest(10_000, account.id(), destination.id())
        );
        TransactionResponse original =
                createExpense(30_000, expenseCategory.getId(), account.id());
        TransactionResponse refund = transactionService.createRefund(
                currentHousehold, original.id(), refundRequest(5_000, null));

        assertApiError(
                ApiErrorCode.INVALID_REQUEST,
                () -> transactionService.createRefund(
                        currentHousehold, original.id(), refundRequest(0, null))
        );
        for (Long invalidId : List.of(income.id(), transfer.id(), refund.id())) {
            assertApiError(
                    ApiErrorCode.TRANSACTION_REFUND_ORIGINAL_REQUIRED,
                    () -> transactionService.createRefund(
                            currentHousehold, invalidId, refundRequest(1_000, null))
            );
        }

        TransactionResponse deleted =
                createExpense(2_000, expenseCategory.getId(), account.id());
        transactionService.delete(currentHousehold, deleted.id(), deleted.version());
        assertApiError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                () -> transactionService.createRefund(
                        currentHousehold, deleted.id(), refundRequest(1_000, null))
        );

        TransactionResponse archiveOriginal =
                createExpense(8_000, expenseCategory.getId(), account.id());
        archive(account);
        archive(expenseCategory);
        TransactionResponse archivedReferenceRefund = transactionService.createRefund(
                currentHousehold,
                archiveOriginal.id(),
                refundRequest(3_000, "보관 기준정보 환불")
        );
        assertThat(archivedReferenceRefund.entries()).singleElement().satisfies(entry -> {
            assertThat(entry.account().archived()).isTrue();
            assertThat(entry.account().id()).isEqualTo(account.id());
        });
        assertThat(archivedReferenceRefund.category().archived()).isTrue();

        AccountResponse corruptionAccount = createAccount(
                "손상 검증 통장", AccountType.CHECKING, AccountNature.ASSET, 10_000);
        Category corruptionCategory = createCategory(CategoryType.EXPENSE, "손상 검증 지출");
        TransactionResponse corrupted =
                createExpense(1_000, corruptionCategory.getId(), corruptionAccount.id());
        jdbcTemplate.update(
                "DELETE FROM transaction_account_entries WHERE transaction_id = ?",
                corrupted.id()
        );
        assertApiError(
                ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID,
                () -> transactionService.createRefund(
                        currentHousehold, corrupted.id(), refundRequest(500, null))
        );
    }

    @Test
    void should_hideForeignOriginal_when_refundRequestedAcrossHouseholds() {
        AccountResponse account = createAccount(
                "현재 통장", AccountType.CHECKING, AccountNature.ASSET, 10_000);
        Category category = createCategory(CategoryType.EXPENSE, "현재 지출");
        TransactionResponse foreignOriginal = createForeignExpense();

        assertApiError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                () -> transactionService.createRefund(
                        currentHousehold, foreignOriginal.id(), refundRequest(1_000, null))
        );
        assertThat(currentBalance(account.id())).isEqualTo(10_000);
        assertThat(category.getHouseholdId()).isEqualTo(currentHousehold.householdId());
    }

    @Test
    void should_preserveLineage_when_originalOrRefundIsMutated() {
        AccountResponse account = createAccount(
                "lineage 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        Category category = createCategory(CategoryType.EXPENSE, "lineage 지출");
        TransactionResponse original = createExpense(50_000, category.getId(), account.id());
        TransactionResponse refund = transactionService.createRefund(
                currentHousehold, original.id(), refundRequest(10_000, "최초 환불"));

        assertApiError(
                ApiErrorCode.TRANSACTION_REFUND_ORIGINAL_HAS_ACTIVE_REFUNDS,
                () -> transactionService.update(
                        currentHousehold,
                        original.id(),
                        updateRequest(
                                original,
                                40_000,
                                account.id(),
                                ORIGINAL_OCCURRED_AT,
                                "금융 변경"
                        )
                )
        );
        assertApiError(
                ApiErrorCode.TRANSACTION_REFUND_ORIGINAL_HAS_ACTIVE_REFUNDS,
                () -> transactionService.delete(
                        currentHousehold, original.id(), original.version())
        );

        TransactionResponse memoUpdated = transactionService.update(
                currentHousehold,
                original.id(),
                updateRequest(
                        original,
                        original.amount(),
                        account.id(),
                        Instant.parse("2026-08-26T03:00:00Z"),
                        "메모만 변경"
                )
        );
        assertThat(memoUpdated.memo()).isEqualTo("메모만 변경");
        assertThat(memoUpdated.occurredAt())
                .isEqualTo(Instant.parse("2026-08-26T03:00:00Z"));
        assertThat(memoUpdated.entries()).singleElement()
                .extracting(TransactionResponse.Entry::balanceDelta)
                .isEqualTo(-50_000L);

        assertApiError(
                ApiErrorCode.TRANSACTION_REFUND_UPDATE_NOT_ALLOWED,
                () -> transactionService.update(
                        currentHousehold,
                        refund.id(),
                        refundUpdateRequest(refund, original.id(), account.id())
                )
        );
        assertApiError(
                ApiErrorCode.TRANSACTION_VERSION_CONFLICT,
                () -> transactionService.delete(
                        currentHousehold, refund.id(), refund.version() + 1)
        );

        transactionService.delete(currentHousehold, refund.id(), refund.version());
        TransactionResponse financiallyUpdated = transactionService.update(
                currentHousehold,
                original.id(),
                updateRequest(
                        memoUpdated,
                        40_000,
                        account.id(),
                        memoUpdated.occurredAt(),
                        memoUpdated.memo()
                )
        );
        assertThat(financiallyUpdated.amount()).isEqualTo(40_000);
        assertThat(transactionService.findRefunds(currentHousehold, original.id()).refunds())
                .isEmpty();
    }

    private Object concurrentRefund(
            Long originalId,
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return transactionService.createRefund(
                    currentHousehold, originalId, refundRequest(70_000, null));
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private void assertDerivedSpending(long expectedSpent, long expectedTransactionCount) {
        CalendarMonthResponse calendar = calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), null, null);
        assertThat(calendar.summary().netSpendingAmount()).isEqualTo(expectedSpent);
        long transactionCount = calendar.days().stream()
                .mapToLong(CalendarMonthResponse.Day::transactionCount)
                .sum();
        assertThat(transactionCount).isEqualTo(expectedTransactionCount);
        BudgetMonthResponse.ScopeBudget householdBudget = budgetService.findMonth(
                        currentHousehold, YearMonth.of(2026, 8))
                .scopes()
                .stream()
                .filter(scope -> scope.scope() == BudgetScope.HOUSEHOLD)
                .findFirst()
                .orElseThrow();
        assertThat(householdBudget.spentAmount()).isEqualTo(expectedSpent);
        BudgetMonthResponse.ScopeBudget personalBudget = budgetService.findMonth(
                        currentHousehold, YearMonth.of(2026, 8))
                .scopes()
                .stream()
                .filter(scope -> scope.scope() == BudgetScope.PERSONAL)
                .filter(scope -> scope.owner() != null
                        && scope.owner().memberId().equals(ownerMemberId))
                .findFirst()
                .orElseThrow();
        assertThat(personalBudget.spentAmount()).isEqualTo(expectedSpent);
        assertThat(budgetService.findMonth(currentHousehold, YearMonth.of(2026, 8))
                .categories())
                .singleElement()
                .satisfies(category -> assertThat(category.spentAmount())
                        .isEqualTo(expectedSpent));
    }

    private void assertSharedSpending(long expectedSpent, long expectedTransactionCount) {
        CalendarMonthResponse calendar = calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                TransactionScope.SHARED,
                null
        );
        assertThat(calendar.summary().netSpendingAmount()).isEqualTo(expectedSpent);
        if (expectedTransactionCount == 2) {
            assertThat(calendar.days()).containsExactly(
                    new CalendarMonthResponse.Day(
                            LocalDate.of(2026, 8, 27), 1, 40_000),
                    new CalendarMonthResponse.Day(
                            LocalDate.of(2026, 8, 28), 1, -15_000)
            );
        } else {
            assertThat(calendar.days()).containsExactly(
                    new CalendarMonthResponse.Day(
                            LocalDate.of(2026, 8, 27), 1, 40_000)
            );
        }

        BudgetMonthResponse budget = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));
        assertThat(budget.scopes())
                .filteredOn(scope -> scope.scope() == BudgetScope.SHARED)
                .singleElement()
                .satisfies(scope -> assertThat(scope.spentAmount()).isEqualTo(expectedSpent));
        assertThat(budget.scopes())
                .filteredOn(scope -> scope.scope() == BudgetScope.PERSONAL)
                .allSatisfy(scope -> assertThat(scope.spentAmount()).isZero());
        assertThat(budget.categories())
                .singleElement()
                .satisfies(category -> {
                    assertThat(category.scope()).isEqualTo(BudgetScope.SHARED);
                    assertThat(category.spentAmount()).isEqualTo(expectedSpent);
                });
    }

    private TransactionResponse createExpense(long amount, Long categoryId, Long accountId) {
        return transactionService.create(
                currentHousehold,
                primaryRequest(TransactionType.EXPENSE, amount, categoryId, accountId)
        );
    }

    private TransactionCreateRequest primaryRequest(
            TransactionType type,
            long amount,
            Long categoryId,
            Long accountId
    ) {
        return new TransactionCreateRequest(
                type,
                amount,
                TransactionScope.PERSONAL,
                ownerMemberId,
                type == TransactionType.EXPENSE ? ownerMemberId : null,
                categoryId,
                accountId,
                null,
                null,
                ORIGINAL_OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private TransactionCreateRequest transferRequest(
            long amount,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        return new TransactionCreateRequest(
                TransactionType.TRANSFER,
                amount,
                null,
                null,
                null,
                null,
                null,
                sourceAccountId,
                destinationAccountId,
                ORIGINAL_OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private RefundCreateRequest refundRequest(long amount, String memo) {
        return new RefundCreateRequest(amount, REFUND_OCCURRED_AT, memo);
    }

    private TransactionUpdateRequest updateRequest(
            TransactionResponse transaction,
            long amount,
            Long accountId,
            Instant occurredAt,
            String memo
    ) {
        return new TransactionUpdateRequest(
                transaction.version(),
                transaction.type(),
                amount,
                transaction.scope(),
                transaction.owner() == null ? null : transaction.owner().memberId(),
                transaction.payer() == null ? null : transaction.payer().memberId(),
                transaction.category() == null ? null : transaction.category().id(),
                accountId,
                null,
                null,
                occurredAt,
                memo,
                transaction.adjustmentType(),
                null
        );
    }

    private TransactionUpdateRequest refundUpdateRequest(
            TransactionResponse refund,
            Long originalId,
            Long accountId
    ) {
        return new TransactionUpdateRequest(
                refund.version(),
                refund.type(),
                refund.amount(),
                refund.scope(),
                refund.owner() == null ? null : refund.owner().memberId(),
                refund.payer() == null ? null : refund.payer().memberId(),
                refund.category().id(),
                accountId,
                null,
                null,
                refund.occurredAt(),
                "수정 시도",
                AdjustmentType.REFUND,
                originalId
        );
    }

    private AccountResponse createAccount(
            String name,
            AccountType type,
            AccountNature nature,
            long openingBalance
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                nature,
                AccountOwnership.PERSONAL,
                ownerMemberId,
                openingBalance,
                LocalDate.of(2026, 8, 1),
                "KRW",
                null,
                type == AccountType.SAVINGS,
                (int) accountRepository.count()
        ));
    }

    private AccountResponse createSharedAccount(
            String name,
            AccountType type,
            AccountNature nature,
            long openingBalance
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                nature,
                AccountOwnership.SHARED,
                null,
                openingBalance,
                LocalDate.of(2026, 8, 1),
                "KRW",
                null,
                type == AccountType.SAVINGS,
                (int) accountRepository.count()
        ));
    }

    private void archive(AccountResponse account) {
        accountService.update(currentHousehold, account.id(), new AccountUpdateRequest(
                account.name(),
                account.institution(),
                account.type(),
                account.nature(),
                account.ownership(),
                account.owner().memberId(),
                account.openingBalance(),
                account.openingBalanceAsOf(),
                account.currency(),
                account.lastFour(),
                account.savingsEnabled(),
                account.sortOrder(),
                true
        ));
    }

    private void archive(Category category) {
        categoryService.update(currentHousehold, category.getId(), new CategoryUpdateRequest(
                category.getGroupId(),
                category.getName(),
                category.getIconKey(),
                category.getColorKey(),
                category.getSortOrder(),
                true
        ));
    }

    private Category createCategory(CategoryType type, String name) {
        categoryService.create(currentHousehold, new CategoryCreateRequest(
                null,
                name,
                type,
                null,
                null,
                (int) categoryRepository.count()
        ));
        return categoryRepository.findAll().stream()
                .filter(category -> category.getName().equals(name))
                .findFirst()
                .orElseThrow();
    }

    private TransactionResponse createForeignExpense() {
        User user = userRepository.saveAndFlush(User.create(
                "foreign-refund@example.test", "Foreign Refund"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Foreign Refund Household"));
        HouseholdMember member = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.OWNER));
        CurrentHousehold foreignCurrent = currentHousehold(user, household);
        AccountResponse foreignAccount = accountService.create(
                foreignCurrent,
                new AccountCreateRequest(
                        "Foreign Account",
                        null,
                        AccountType.CHECKING,
                        AccountNature.ASSET,
                        AccountOwnership.PERSONAL,
                        member.getId(),
                        10_000L,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        null,
                        false,
                        0
                )
        );
        categoryService.create(foreignCurrent, new CategoryCreateRequest(
                null, "Foreign Expense", CategoryType.EXPENSE, null, null, 0));
        Category foreignCategory = categoryRepository.findAll().stream()
                .filter(category -> category.getHouseholdId().equals(household.getId()))
                .findFirst()
                .orElseThrow();
        return transactionService.create(
                foreignCurrent,
                new TransactionCreateRequest(
                        TransactionType.EXPENSE,
                        2_000L,
                        TransactionScope.PERSONAL,
                        member.getId(),
                        member.getId(),
                        foreignCategory.getId(),
                        foreignAccount.id(),
                        null,
                        null,
                        ORIGINAL_OCCURRED_AT,
                        null,
                        AdjustmentType.NORMAL,
                        null
                )
        );
    }

    private CurrentHousehold currentHousehold(User user, Household household) {
        return new CurrentHousehold(
                user.getId(),
                user.getEmail(),
                user.getDisplayName(),
                household.getId(),
                household.getName(),
                household.getBaseCurrency(),
                household.getTimezone(),
                HouseholdRole.OWNER
        );
    }

    private long currentBalance(Long accountId) {
        return accountService.findAll(currentHousehold, true).stream()
                .filter(account -> account.id().equals(accountId))
                .findFirst()
                .orElseThrow()
                .currentBalance();
    }

    private void assertApiError(ApiErrorCode code, Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo(code)
                );
    }

    private void clearDatabase() {
        budgetRepository.deleteAllInBatch();
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        categoryGroupRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }
}
