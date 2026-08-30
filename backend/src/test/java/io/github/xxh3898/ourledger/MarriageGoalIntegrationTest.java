package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountBalanceService;
import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.goal.GoalAccountRepository;
import io.github.xxh3898.ourledger.goal.GoalProjectionStatus;
import io.github.xxh3898.ourledger.goal.GoalRepository;
import io.github.xxh3898.ourledger.goal.MarriageGoalCreateRequest;
import io.github.xxh3898.ourledger.goal.MarriageGoalService;
import io.github.xxh3898.ourledger.goal.MarriageGoalUpdateRequest;
import io.github.xxh3898.ourledger.goal.MarriageGoalViewResponse;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.RefundCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.reset;

@ActiveProfiles("test")
@Import({
        TestcontainersConfiguration.class,
        MarriageGoalIntegrationTest.FixedClockConfiguration.class
})
@SpringBootTest
class MarriageGoalIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-08-28T03:00:00Z");

    @Autowired private MarriageGoalService goalService;
    @Autowired private GoalRepository goalRepository;
    @Autowired private GoalAccountRepository goalAccountRepository;
    @MockitoSpyBean private AccountService accountService;
    @MockitoSpyBean private AccountBalanceService accountBalanceService;
    @Autowired private TransactionService transactionService;
    @Autowired private CategoryRepository categoryRepository;
    @Autowired private UserRepository userRepository;
    @Autowired private HouseholdRepository householdRepository;
    @Autowired private HouseholdMemberRepository householdMemberRepository;
    @Autowired private JdbcTemplate jdbcTemplate;

    private Fixture fixture;
    private Long expenseCategoryId;
    private Long incomeCategoryId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        fixture = createFixture("goal-owner@example.test", "Goal Household");
        expenseCategoryId = createCategory("지출", CategoryType.EXPENSE).getId();
        incomeCategoryId = createCategory("수입", CategoryType.INCOME).getId();
    }

    @AfterEach
    void tearDown() {
        reset(accountService, accountBalanceService);
        clearDatabase();
    }

    @Test
    void should_returnNormalEmptyStateAndValidateCreateUpdate_when_goalLifecycleRuns() {
        AccountResponse eligible = createAccount(
                fixture, "저축 통장", AccountType.SAVINGS,
                AccountNature.ASSET, 1_000_000, true);
        createAccount(
                fixture, "일반 통장", AccountType.CHECKING,
                AccountNature.ASSET, 1_000_000, false);

        MarriageGoalViewResponse empty = goalService.find(fixture.currentHousehold());
        assertThat(empty.goal()).isNull();
        assertThat(empty.eligibleAccounts()).singleElement()
                .extracting(MarriageGoalViewResponse.EligibleAccount::id)
                .isEqualTo(eligible.id());

        MarriageGoalViewResponse created = createGoal("우리 집", 100_000_000);
        assertThat(created.goal().version()).isZero();
        assertThat(created.goal().currentAmount()).isZero();
        assertThat(created.goal().projectionStatus())
                .isEqualTo(GoalProjectionStatus.INSUFFICIENT_HISTORY);

        MarriageGoalViewResponse updated = goalService.update(
                fixture.currentHousehold(),
                new MarriageGoalUpdateRequest(
                        created.goal().version(), "우리 보금자리", 120_000_000L)
        );
        assertThat(updated.goal().name()).isEqualTo("우리 보금자리");
        assertThat(updated.goal().targetAmount()).isEqualTo(120_000_000);
        assertThat(updated.goal().version()).isEqualTo(1);

        assertApiError(
                ApiErrorCode.GOAL_VERSION_CONFLICT,
                () -> goalService.update(
                        fixture.currentHousehold(),
                        new MarriageGoalUpdateRequest(0L, "stale", 1L))
        );
        assertApiError(
                ApiErrorCode.GOAL_ALREADY_EXISTS,
                () -> createGoal("중복", 1_000_000)
        );
        assertThatThrownBy(() -> createGoal(" ", 0))
                .isInstanceOf(ApiException.class)
                .extracting(exception -> ((ApiException) exception).code())
                .isEqualTo(ApiErrorCode.INVALID_REQUEST);
    }

    @Test
    void should_enforceEligibilityHouseholdBoundaryArchiveAndUnlink_when_accountsChange() {
        createGoal("연결 검증", 10_000_000);
        AccountResponse eligible = createAccount(
                fixture, "연결 저축", AccountType.SAVINGS,
                AccountNature.ASSET, 1_000_000, true);
        AccountResponse disabled = createAccount(
                fixture, "비저축", AccountType.CHECKING,
                AccountNature.ASSET, 500_000, false);
        AccountResponse liability = createAccount(
                fixture, "카드", AccountType.CREDIT_CARD,
                AccountNature.LIABILITY, 0, false);
        Fixture foreign = createFixture("goal-foreign@example.test", "Foreign Household");
        AccountResponse foreignAccount = createAccount(
                foreign, "외부 저축", AccountType.SAVINGS,
                AccountNature.ASSET, 9_000_000, true);

        assertApiError(
                ApiErrorCode.GOAL_ACCOUNT_NOT_ELIGIBLE,
                () -> goalService.linkAccount(fixture.currentHousehold(), disabled.id())
        );
        assertApiError(
                ApiErrorCode.GOAL_ACCOUNT_NOT_ELIGIBLE,
                () -> goalService.linkAccount(fixture.currentHousehold(), liability.id())
        );
        assertApiError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                () -> goalService.linkAccount(
                        fixture.currentHousehold(), foreignAccount.id())
        );

        MarriageGoalViewResponse linked = goalService.linkAccount(
                fixture.currentHousehold(), eligible.id());
        assertThat(linked.goal().currentAmount()).isEqualTo(1_000_000);
        assertThat(linked.goal().linkedAccounts()).singleElement().satisfies(account -> {
            assertThat(account.startingBalance()).isEqualTo(1_000_000);
            assertThat(account.archived()).isFalse();
        });

        archiveAccount(fixture, eligible);
        MarriageGoalViewResponse archived = goalService.find(fixture.currentHousehold());
        assertThat(archived.goal().currentAmount()).isEqualTo(1_000_000);
        assertThat(archived.goal().linkedAccounts()).singleElement()
                .extracting(MarriageGoalViewResponse.LinkedAccount::archived)
                .isEqualTo(true);

        long transactionCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM transactions", Long.class);
        goalService.unlinkAccount(fixture.currentHousehold(), eligible.id());
        MarriageGoalViewResponse unlinked = goalService.find(fixture.currentHousehold());
        assertThat(unlinked.goal().currentAmount()).isZero();
        assertThat(unlinked.goal().linkedAccounts()).isEmpty();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM transactions", Long.class)).isEqualTo(transactionCount);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM accounts WHERE id = ?", Long.class, eligible.id()))
                .isEqualTo(1);
    }

    @Test
    void should_useActualLedgerBalanceAndOnlyGoalBoundaryTransfers_when_readModelIsBuilt() {
        createGoal("원장 목표", 10_000_000);
        AccountResponse outside = createAccount(
                fixture, "생활 통장", AccountType.CHECKING,
                AccountNature.ASSET, 5_000_000, true);
        AccountResponse firstGoal = createAccount(
                fixture, "결혼 적금", AccountType.SAVINGS,
                AccountNature.ASSET, 1_000_000, true);
        AccountResponse secondGoal = createAccount(
                fixture, "공동 적금", AccountType.SAVINGS,
                AccountNature.ASSET, 0, true);

        transfer(30_000, outside.id(), firstGoal.id(), "2026-08-01T03:00:00Z", "연결 전");
        goalService.linkAccount(fixture.currentHousehold(), firstGoal.id());
        goalService.linkAccount(fixture.currentHousehold(), secondGoal.id());
        jdbcTemplate.update(
                "UPDATE goal_accounts SET linked_at = TIMESTAMPTZ '2026-08-02 00:00:00+09'"
        );
        transfer(100_000, outside.id(), firstGoal.id(), "2026-08-20T03:00:00Z", "저축");
        transfer(20_000, firstGoal.id(), outside.id(), "2026-08-21T03:00:00Z", "인출");
        transfer(10_000, firstGoal.id(), secondGoal.id(), "2026-08-22T03:00:00Z", "내부 이동");
        TransactionResponse deleted = transfer(
                500_000, outside.id(), firstGoal.id(), "2026-08-23T03:00:00Z", "삭제");
        transactionService.delete(
                fixture.currentHousehold(), deleted.id(), deleted.version());
        income(firstGoal.id(), 50_000, "2026-08-24T03:00:00Z");
        TransactionResponse expense = expense(
                firstGoal.id(), 10_000, "2026-08-25T03:00:00Z");
        transactionService.createRefund(
                fixture.currentHousehold(),
                expense.id(),
                new RefundCreateRequest(
                        4_000L,
                        Instant.parse("2026-08-26T03:00:00Z"),
                        "환불"
                )
        );

        MarriageGoalViewResponse.MarriageGoal goal = goalService
                .find(fixture.currentHousehold()).goal();

        assertThat(goal.currentAmount()).isEqualTo(1_154_000);
        assertThat(goal.thisMonthSavingsAmount()).isEqualTo(80_000);
        assertThat(goal.monthlyTrend()).hasSize(6);
        assertThat(goal.recentSavingsActivities())
                .extracting(MarriageGoalViewResponse.SavingsActivity::savingsImpactAmount)
                .containsExactly(-20_000L, 100_000L);
        assertThat(goal.recentSavingsActivities())
                .noneMatch(activity -> activity.memo().equals("연결 전")
                        || activity.memo().equals("내부 이동")
                        || activity.memo().equals("삭제"));
    }

    @Test
    void should_calculateSixMonthTrendCompletedAverageProjectionAndRecurringProvenance() {
        createGoal("예상 목표", 1_000_000);
        AccountResponse outside = createAccount(
                fixture, "급여 통장", AccountType.CHECKING,
                AccountNature.ASSET, 2_000_000, false);
        AccountResponse goalAccount = createAccount(
                fixture, "목표 통장", AccountType.SAVINGS,
                AccountNature.ASSET, 0, true);
        goalService.linkAccount(fixture.currentHousehold(), goalAccount.id());
        jdbcTemplate.update(
                "UPDATE goal_accounts SET linked_at = TIMESTAMPTZ '2026-04-01 00:00:00+09'"
        );

        transfer(10_000, outside.id(), goalAccount.id(), "2026-05-10T03:00:00Z", "5월");
        transfer(20_000, outside.id(), goalAccount.id(), "2026-06-10T03:00:00Z", "6월");
        transfer(30_000, outside.id(), goalAccount.id(), "2026-07-10T03:00:00Z", "7월");
        TransactionResponse recurring = transfer(
                40_000, outside.id(), goalAccount.id(), "2026-08-10T03:00:00Z", "8월 반복");
        Long recurringId = insertRecurringRule();
        jdbcTemplate.update(
                """
                UPDATE transactions
                SET generated_from_recurring_id = ?, recurrence_date = DATE '2026-08-10'
                WHERE id = ?
                """,
                recurringId, recurring.id()
        );

        MarriageGoalViewResponse.MarriageGoal goal = goalService
                .find(fixture.currentHousehold()).goal();

        assertThat(goal.monthlyTrend())
                .extracting(MarriageGoalViewResponse.MonthlyTrend::savingsAmount)
                .containsExactly(0L, 0L, 10_000L, 20_000L, 30_000L, 40_000L);
        assertThat(goal.recentAverageMonthlySavingsAmount()).isEqualTo(20_000);
        assertThat(goal.projectionStatus()).isEqualTo(GoalProjectionStatus.PROJECTED);
        assertThat(goal.expectedAchievementMonth()).isEqualTo(YearMonth.of(2030, 5));
        assertThat(goal.recentSavingsActivities().getFirst().generatedFromRecurringId())
                .isEqualTo(recurringId);
        assertThat(goal.recentSavingsActivities().getFirst().recurrenceDate())
                .isEqualTo(LocalDate.of(2026, 8, 10));
    }

    @Test
    @Timeout(30)
    void should_allowExactlyOneMarriageGoal_when_postgresqlCreatesRace() throws Exception {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Object> first = executor.submit(() -> concurrentCreate(ready, start));
            Future<Object> second = executor.submit(() -> concurrentCreate(ready, start));
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<Object> results = List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS)
            );
            assertThat(results).filteredOn(MarriageGoalViewResponse.class::isInstance)
                    .hasSize(1);
            assertThat(results).filteredOn(ApiErrorCode.GOAL_ALREADY_EXISTS::equals)
                    .hasSize(1);
            assertThat(goalRepository.count()).isEqualTo(1);
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    @Test
    @Timeout(30)
    void should_allowExactlyOneAccountLink_when_postgresqlLinksRace() throws Exception {
        createGoal("연결 경합", 10_000_000);
        AccountResponse account = createAccount(
                fixture, "경합 저축", AccountType.SAVINGS,
                AccountNature.ASSET, 100_000, true);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Object> first = executor.submit(
                    () -> concurrentLink(account.id(), ready, start));
            Future<Object> second = executor.submit(
                    () -> concurrentLink(account.id(), ready, start));
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<Object> results = List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS)
            );
            assertThat(results).filteredOn(MarriageGoalViewResponse.class::isInstance)
                    .hasSize(1);
            assertThat(results).filteredOn(ApiErrorCode.GOAL_ACCOUNT_ALREADY_ASSIGNED::equals)
                    .hasSize(1);
            assertThat(goalAccountRepository.count()).isEqualTo(1);
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    @Test
    @Timeout(30)
    void should_serializeLinkSnapshotAndConcurrentPosting_when_sameAccountRowContends()
            throws Exception {
        createGoal("스냅샷 경합", 10_000_000);
        AccountResponse goalAccount = createAccount(
                fixture, "경합 목표", AccountType.SAVINGS,
                AccountNature.ASSET, 100_000, true);
        AccountResponse outside = createAccount(
                fixture, "경합 외부", AccountType.CHECKING,
                AccountNature.ASSET, 500_000, false);
        CountDownLatch linkHasAccountLock = new CountDownLatch(1);
        CountDownLatch allowLinkCommit = new CountDownLatch(1);
        CountDownLatch postingAttemptedAccountLock = new CountDownLatch(1);
        AtomicBoolean blockLinkSnapshotOnce = new AtomicBoolean(true);

        doAnswer(invocation -> {
            long balance = (long) invocation.callRealMethod();
            if (Thread.currentThread().getName().equals("goal-link")
                    && blockLinkSnapshotOnce.compareAndSet(true, false)) {
                linkHasAccountLock.countDown();
                awaitLatch(allowLinkCommit, "Goal link release");
            }
            return balance;
        }).when(accountBalanceService).currentBalance(any(Account.class));
        doAnswer(invocation -> {
            Long requestedId = invocation.getArgument(1);
            if (Thread.currentThread().getName().equals("goal-posting")
                    && requestedId.equals(goalAccount.id())) {
                postingAttemptedAccountLock.countDown();
            }
            return invocation.callRealMethod();
        }).when(accountService).requireAccountForPosting(anyLong(), anyLong());

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<MarriageGoalViewResponse> link = executor.submit(() -> {
                Thread.currentThread().setName("goal-link");
                return goalService.linkAccount(
                        fixture.currentHousehold(), goalAccount.id());
            });
            awaitLatch(linkHasAccountLock, "Goal Account lock");

            Future<TransactionResponse> posting = executor.submit(() -> {
                Thread.currentThread().setName("goal-posting");
                return transfer(
                        50_000,
                        outside.id(),
                        goalAccount.id(),
                        "2026-08-28T03:00:01Z",
                        "동시 posting"
                );
            });
            awaitLatch(postingAttemptedAccountLock, "posting Account lock attempt");
            assertThatThrownBy(() -> posting.get(250, TimeUnit.MILLISECONDS))
                    .isInstanceOf(TimeoutException.class);

            allowLinkCommit.countDown();
            link.get(10, TimeUnit.SECONDS);
            posting.get(10, TimeUnit.SECONDS);

            assertThat(jdbcTemplate.queryForObject(
                    "SELECT starting_balance FROM goal_accounts WHERE account_id = ?",
                    Long.class,
                    goalAccount.id()
            )).isEqualTo(100_000);
            assertThat(goalService.find(fixture.currentHousehold()).goal().currentAmount())
                    .isEqualTo(150_000);
        } finally {
            allowLinkCommit.countDown();
            executor.shutdownNow();
        }
    }

    @Test
    @Timeout(30)
    void should_returnOneVersionConflict_when_targetPatchesRace() throws Exception {
        MarriageGoalViewResponse created = createGoal("수정 경합", 10_000_000);
        Long version = created.goal().version();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Object> first = executor.submit(
                    () -> concurrentUpdate("첫 수정", 20_000_000, version, ready, start));
            Future<Object> second = executor.submit(
                    () -> concurrentUpdate("둘째 수정", 30_000_000, version, ready, start));
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<Object> results = List.of(
                    first.get(10, TimeUnit.SECONDS),
                    second.get(10, TimeUnit.SECONDS)
            );
            assertThat(results).filteredOn(MarriageGoalViewResponse.class::isInstance)
                    .hasSize(1);
            assertThat(results).filteredOn(ApiErrorCode.GOAL_VERSION_CONFLICT::equals)
                    .hasSize(1);
            assertThat(goalService.find(fixture.currentHousehold()).goal().version())
                    .isEqualTo(version + 1);
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    private Object concurrentCreate(CountDownLatch ready, CountDownLatch start)
            throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return createGoal("동시 목표", 10_000_000);
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private Object concurrentLink(Long accountId, CountDownLatch ready, CountDownLatch start)
            throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return goalService.linkAccount(fixture.currentHousehold(), accountId);
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private Object concurrentUpdate(
            String name,
            long targetAmount,
            Long version,
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return goalService.update(
                    fixture.currentHousehold(),
                    new MarriageGoalUpdateRequest(version, name, targetAmount)
            );
        } catch (ApiException exception) {
            return exception.code();
        }
    }

    private MarriageGoalViewResponse createGoal(String name, long targetAmount) {
        return goalService.create(
                fixture.currentHousehold(),
                new MarriageGoalCreateRequest(name, targetAmount)
        );
    }

    private AccountResponse createAccount(
            Fixture targetFixture,
            String name,
            AccountType type,
            AccountNature nature,
            long openingBalance,
            boolean savingsEnabled
    ) {
        return accountService.create(
                targetFixture.currentHousehold(),
                new AccountCreateRequest(
                        name,
                        null,
                        type,
                        nature,
                        AccountOwnership.PERSONAL,
                        targetFixture.memberId(),
                        openingBalance,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        null,
                        savingsEnabled,
                        0
                )
        );
    }

    private void archiveAccount(Fixture targetFixture, AccountResponse account) {
        accountService.update(
                targetFixture.currentHousehold(),
                account.id(),
                new AccountUpdateRequest(
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
                )
        );
    }

    private TransactionResponse transfer(
            long amount,
            Long sourceAccountId,
            Long destinationAccountId,
            String occurredAt,
            String memo
    ) {
        return transactionService.create(
                fixture.currentHousehold(),
                new TransactionCreateRequest(
                        TransactionType.TRANSFER,
                        amount,
                        null,
                        null,
                        null,
                        null,
                        null,
                        sourceAccountId,
                        destinationAccountId,
                        Instant.parse(occurredAt),
                        memo,
                        AdjustmentType.NORMAL,
                        null
                )
        );
    }

    private TransactionResponse income(Long accountId, long amount, String occurredAt) {
        return transactionService.create(
                fixture.currentHousehold(),
                new TransactionCreateRequest(
                        TransactionType.INCOME,
                        amount,
                        TransactionScope.PERSONAL,
                        fixture.memberId(),
                        null,
                        incomeCategoryId,
                        accountId,
                        null,
                        null,
                        Instant.parse(occurredAt),
                        "직접 입금",
                        AdjustmentType.NORMAL,
                        null
                )
        );
    }

    private TransactionResponse expense(Long accountId, long amount, String occurredAt) {
        return transactionService.create(
                fixture.currentHousehold(),
                new TransactionCreateRequest(
                        TransactionType.EXPENSE,
                        amount,
                        TransactionScope.PERSONAL,
                        fixture.memberId(),
                        null,
                        expenseCategoryId,
                        accountId,
                        null,
                        null,
                        Instant.parse(occurredAt),
                        "직접 지출",
                        AdjustmentType.NORMAL,
                        null
                )
        );
    }

    private Category createCategory(String name, CategoryType type) {
        return categoryRepository.saveAndFlush(Category.create(
                fixture.householdId(),
                null,
                name,
                type,
                null,
                null,
                0
        ));
    }

    private Fixture createFixture(String email, String householdName) {
        User user = userRepository.saveAndFlush(User.create(email, "Goal Owner"));
        Household household = householdRepository.saveAndFlush(
                Household.create(householdName));
        HouseholdMember member = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.OWNER));
        return new Fixture(
                household.getId(),
                member.getId(),
                new CurrentHousehold(
                        user.getId(),
                        user.getEmail(),
                        user.getDisplayName(),
                        household.getId(),
                        household.getName(),
                        household.getBaseCurrency(),
                        household.getTimezone(),
                        HouseholdRole.OWNER
                )
        );
    }

    private Long insertRecurringRule() {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO recurring_transactions (
                    household_id, name, type, amount,
                    frequency, interval_value, start_date, scheduled_local_time,
                    auto_post, active, next_recurrence_date,
                    version, created_by, updated_by
                ) VALUES (?, '목표 반복 저축', 'TRANSFER', 40000,
                          'MONTHLY', 1, DATE '2026-08-10', TIME '09:00',
                          TRUE, TRUE, DATE '2026-09-10', 0, ?, ?)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), fixture.memberId(), fixture.memberId()
        );
    }

    private void assertApiError(ApiErrorCode code, Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo(code));
    }

    private void awaitLatch(CountDownLatch latch, String name) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Timed out waiting for " + name);
        }
    }

    private void clearDatabase() {
        jdbcTemplate.execute("""
                TRUNCATE TABLE
                    goal_accounts,
                    goals,
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

    private record Fixture(
            Long householdId,
            Long memberId,
            CurrentHousehold currentHousehold
    ) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedGoalClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
