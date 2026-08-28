package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.budget.BudgetRepository;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.statistics.SavingsActivityResponse;
import io.github.xxh3898.ourledger.statistics.StatisticsFilter;
import io.github.xxh3898.ourledger.statistics.StatisticsResponse;
import io.github.xxh3898.ourledger.statistics.StatisticsService;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.RefundCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.groups.Tuple.tuple;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class StatisticsIntegrationTest {

    @Autowired
    private StatisticsService statisticsService;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private AccountService accountService;

    @Autowired
    private BudgetRepository budgetRepository;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private CategoryGroupRepository categoryGroupRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private UserRepository userRepository;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long partnerMemberId;
    private Long incomeCategoryId;
    private Long foodCategoryId;
    private Long archivedCategoryId;
    private Long checkingAccountId;
    private Long otherCheckingAccountId;
    private Long savingsAccountId;
    private Long otherSavingsAccountId;
    private Long cardAccountId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        User owner = userRepository.saveAndFlush(
                User.create("statistics-owner@example.test", "Owner"));
        User partner = userRepository.saveAndFlush(
                User.create("statistics-partner@example.test", "Partner"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Statistics Household"));
        HouseholdMember ownerMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));
        HouseholdMember partnerMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, partner, HouseholdRole.MEMBER));
        ownerMemberId = ownerMember.getId();
        partnerMemberId = partnerMember.getId();
        currentHousehold = new CurrentHousehold(
                owner.getId(),
                owner.getEmail(),
                owner.getDisplayName(),
                household.getId(),
                household.getName(),
                household.getBaseCurrency(),
                household.getTimezone(),
                HouseholdRole.OWNER
        );

        incomeCategoryId = category("급여", CategoryType.INCOME, 0).getId();
        foodCategoryId = category("식비", CategoryType.EXPENSE, 1).getId();
        archivedCategoryId = category("취미", CategoryType.EXPENSE, 2).getId();
        checkingAccountId = account("생활비", AccountType.CHECKING, AccountNature.ASSET, false, 0);
        otherCheckingAccountId = account(
                "비상금", AccountType.CHECKING, AccountNature.ASSET, false, 1);
        savingsAccountId = account("결혼 적금", AccountType.SAVINGS, AccountNature.ASSET, true, 2);
        otherSavingsAccountId = account(
                "여행 적금", AccountType.SAVINGS, AccountNature.ASSET, true, 3);
        cardAccountId = account(
                "생활 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY, false, 4);
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_deriveSummaryBreakdownsAndSavingsActivities_when_ledgerContainsRefundCardAndTransfers() {
        income(3_000_000, ownerMemberId, "2026-08-01T00:00:00Z");
        TransactionResponse original = expense(
                100_000, ownerMemberId, foodCategoryId, checkingAccountId,
                "2026-08-02T00:00:00Z");
        transactionService.createRefund(currentHousehold, original.id(), new RefundCreateRequest(
                20_000L, Instant.parse("2026-08-03T00:00:00Z"), "부분 환불"));
        expense(
                50_000, partnerMemberId, archivedCategoryId, cardAccountId,
                "2026-08-04T00:00:00Z");
        sharedExpense(30_000, foodCategoryId, checkingAccountId, "2026-08-05T00:00:00Z");
        expense(
                10_000, ownerMemberId, foodCategoryId, savingsAccountId,
                "2026-08-06T00:00:00Z");
        transfer(50_000, checkingAccountId, cardAccountId, "2026-08-07T00:00:00Z", "카드대금");
        transfer(1_000_000, checkingAccountId, savingsAccountId, "2026-08-08T00:00:00Z", "저축");
        transfer(100_000, savingsAccountId, checkingAccountId, "2026-08-09T00:00:00Z", "인출");
        transfer(70_000, savingsAccountId, otherSavingsAccountId, "2026-08-10T00:00:00Z", "저축 이동");
        transfer(30_000, checkingAccountId, otherCheckingAccountId, "2026-08-11T00:00:00Z", "일반 이동");
        archiveCategory(archivedCategoryId);
        archiveAccount(cardAccountId);

        TransactionResponse deletedIncome = income(
                9_000_000, ownerMemberId, "2026-08-12T00:00:00Z");
        transactionService.delete(currentHousehold, deletedIncome.id(), deletedIncome.version());
        TransactionResponse deletedExpense = expense(
                99_000, ownerMemberId, foodCategoryId, checkingAccountId,
                "2026-08-13T00:00:00Z");
        transactionService.delete(currentHousehold, deletedExpense.id(), deletedExpense.version());
        TransactionResponse deletedTransfer = transfer(
                500_000, checkingAccountId, savingsAccountId,
                "2026-08-14T00:00:00Z", "삭제된 저축");
        transactionService.delete(currentHousehold, deletedTransfer.id(), deletedTransfer.version());

        StatisticsResponse response = statisticsService.find(
                currentHousehold,
                filter(LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31))
        );

        assertThat(response.summary().incomeAmount()).isEqualTo(3_000_000);
        assertThat(response.summary().netSpendingAmount()).isEqualTo(170_000);
        assertThat(response.summary().savingsAmount()).isEqualTo(900_000);
        assertThat(response.summary().savingsRate())
                .isEqualByComparingTo(new BigDecimal("30.0"));
        assertThat(response.subjects())
                .extracting(
                        item -> item.owner() == null ? null : item.owner().displayName(),
                        StatisticsResponse.Subject::scope,
                        StatisticsResponse.Subject::netSpendingAmount
                )
                .containsExactly(
                        tuple("Owner", TransactionScope.PERSONAL, 90_000L),
                        tuple("Partner", TransactionScope.PERSONAL, 50_000L),
                        tuple(null, TransactionScope.SHARED, 30_000L)
                );
        assertThat(response.subjects().stream()
                .mapToLong(StatisticsResponse.Subject::netSpendingAmount)
                .sum()).isEqualTo(response.summary().netSpendingAmount());
        assertThat(response.categories())
                .extracting(
                        item -> item.category().name(),
                        item -> item.category().archived(),
                        StatisticsResponse.CategoryBreakdown::netSpendingAmount
                )
                .containsExactly(
                        tuple("식비", false, 120_000L),
                        tuple("취미", true, 50_000L)
                );
        assertThat(response.categories().getFirst().shareRate())
                .isEqualByComparingTo(new BigDecimal("70.6"));
        assertThat(response.accounts())
                .extracting(
                        item -> item.account().name(),
                        item -> item.account().archived(),
                        StatisticsResponse.AccountBreakdown::netSpendingAmount
                )
                .containsExactly(
                        tuple("생활비", false, 110_000L),
                        tuple("생활 카드", true, 50_000L),
                        tuple("결혼 적금", false, 10_000L)
                );
        assertThat(response.accounts().stream()
                .mapToLong(StatisticsResponse.AccountBreakdown::netSpendingAmount)
                .sum()).isEqualTo(response.summary().netSpendingAmount());

        assertThat(response.months()).singleElement().satisfies(month -> {
            assertThat(month.month()).isEqualTo(YearMonth.of(2026, 8));
            assertThat(month.savingsAmount()).isEqualTo(900_000);
        });
        assertThat(statisticsService.findSavingsActivities(
                currentHousehold,
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31)
        )).extracting(
                SavingsActivityResponse::savingsImpactAmount,
                item -> item.sourceAccount().name(),
                item -> item.destinationAccount().name()
        ).containsExactly(
                tuple(-100_000L, "결혼 적금", "생활비"),
                tuple(1_000_000L, "생활비", "결혼 적금")
        );
    }

    @Test
    void should_isolatePersonalAndSharedMetrics_when_scopeChanges() {
        income(500_000, ownerMemberId, "2026-08-01T00:00:00Z");
        income(300_000, partnerMemberId, "2026-08-01T01:00:00Z");
        expense(100_000, ownerMemberId, foodCategoryId, checkingAccountId, "2026-08-02T00:00:00Z");
        expense(70_000, partnerMemberId, foodCategoryId, checkingAccountId, "2026-08-03T00:00:00Z");
        sharedExpense(40_000, foodCategoryId, checkingAccountId, "2026-08-04T00:00:00Z");
        transfer(200_000, checkingAccountId, savingsAccountId, "2026-08-05T00:00:00Z", null);

        StatisticsResponse owner = statisticsService.find(currentHousehold, new StatisticsFilter(
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31),
                null,
                null,
                TransactionScope.PERSONAL,
                ownerMemberId
        ));
        StatisticsResponse partner = statisticsService.find(currentHousehold, new StatisticsFilter(
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31),
                null,
                null,
                TransactionScope.PERSONAL,
                partnerMemberId
        ));
        StatisticsResponse shared = statisticsService.find(currentHousehold, new StatisticsFilter(
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31),
                null,
                null,
                TransactionScope.SHARED,
                null
        ));

        assertThat(owner.summary())
                .extracting(
                        StatisticsResponse.Summary::incomeAmount,
                        StatisticsResponse.Summary::netSpendingAmount,
                        StatisticsResponse.Summary::savingsAmount,
                        StatisticsResponse.Summary::savingsRate
                ).containsExactly(500_000L, 100_000L, null, null);
        assertThat(partner.summary())
                .extracting(
                        StatisticsResponse.Summary::incomeAmount,
                        StatisticsResponse.Summary::netSpendingAmount,
                        StatisticsResponse.Summary::savingsAmount
                ).containsExactly(300_000L, 70_000L, null);
        assertThat(shared.summary())
                .extracting(
                        StatisticsResponse.Summary::incomeAmount,
                        StatisticsResponse.Summary::netSpendingAmount,
                        StatisticsResponse.Summary::savingsAmount
                ).containsExactly(0L, 40_000L, null);
        assertThat(owner.subjects()).singleElement()
                .extracting(item -> item.owner().memberId())
                .isEqualTo(ownerMemberId);
        assertThat(shared.subjects()).singleElement()
                .extracting(StatisticsResponse.Subject::scope)
                .isEqualTo(TransactionScope.SHARED);
    }

    @Test
    void should_calculateComparisonAndNullPercentages_when_previousDenominatorIsZero() {
        income(100_000, ownerMemberId, "2026-08-01T00:00:00Z");
        expense(50_000, ownerMemberId, foodCategoryId, checkingAccountId, "2026-08-02T00:00:00Z");
        transfer(10_000, checkingAccountId, savingsAccountId, "2026-08-03T00:00:00Z", null);
        expense(100_000, ownerMemberId, foodCategoryId, checkingAccountId, "2026-07-02T00:00:00Z");

        StatisticsResponse response = statisticsService.find(
                currentHousehold,
                new StatisticsFilter(
                        LocalDate.of(2026, 8, 1),
                        LocalDate.of(2026, 8, 31),
                        LocalDate.of(2026, 7, 1),
                        LocalDate.of(2026, 7, 31),
                        null,
                        null
                )
        );

        assertThat(response.comparison()).isNotNull();
        assertThat(response.comparison().incomeAmount()).isZero();
        assertThat(response.comparison().netSpendingAmount()).isEqualTo(100_000);
        assertThat(response.comparison().savingsAmount()).isZero();
        assertThat(response.comparison().incomeDifferenceAmount()).isEqualTo(100_000);
        assertThat(response.comparison().netSpendingDifferenceAmount()).isEqualTo(-50_000);
        assertThat(response.comparison().savingsDifferenceAmount()).isEqualTo(10_000);
        assertThat(response.comparison().incomePercentChange()).isNull();
        assertThat(response.comparison().netSpendingPercentChange())
                .isEqualByComparingTo(new BigDecimal("-50.0"));
        assertThat(response.comparison().savingsPercentChange()).isNull();
        assertThat(response.comparison().savingsRate()).isNull();
        assertThat(response.comparison().savingsRateDifferencePoints()).isNull();
    }

    @Test
    void should_applyHouseholdTimezoneAndReturnEmptyMonths_when_customRangeHasPartialMonths() {
        income(100_000, ownerMemberId, "2026-06-14T14:59:59Z");
        income(200_000, ownerMemberId, "2026-06-14T15:00:00Z");
        expense(30_000, ownerMemberId, foodCategoryId, checkingAccountId, "2026-08-20T14:59:59Z");
        expense(90_000, ownerMemberId, foodCategoryId, checkingAccountId, "2026-08-20T15:00:00Z");

        StatisticsResponse response = statisticsService.find(
                currentHousehold,
                filter(LocalDate.of(2026, 6, 15), LocalDate.of(2026, 8, 20))
        );

        assertThat(response.summary().incomeAmount()).isEqualTo(200_000);
        assertThat(response.summary().netSpendingAmount()).isEqualTo(30_000);
        assertThat(response.months())
                .extracting(
                        StatisticsResponse.MonthTrend::month,
                        StatisticsResponse.MonthTrend::incomeAmount,
                        StatisticsResponse.MonthTrend::netSpendingAmount
                )
                .containsExactly(
                        tuple(YearMonth.of(2026, 6), 200_000L, 0L),
                        tuple(YearMonth.of(2026, 7), 0L, 0L),
                        tuple(YearMonth.of(2026, 8), 0L, 30_000L)
                );
        assertThat(response.months().get(1).savingsRate()).isNull();
    }

    @Test
    void should_rejectInvalidRangesAndHideForeignMember_when_filterIsInvalid() {
        assertBadRequest(new StatisticsFilter(
                null, LocalDate.of(2026, 8, 31), null, null, null, null));
        assertBadRequest(new StatisticsFilter(
                LocalDate.of(2026, 9, 1), LocalDate.of(2026, 8, 31),
                null, null, null, null));
        assertBadRequest(new StatisticsFilter(
                LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31),
                LocalDate.of(2026, 7, 1), null, null, null));
        assertBadRequest(new StatisticsFilter(
                LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31),
                null, null, null, ownerMemberId));
        assertBadRequest(new StatisticsFilter(
                LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31),
                null, null, TransactionScope.PERSONAL, null));
        assertBadRequest(new StatisticsFilter(
                LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31),
                null, null, TransactionScope.SHARED, ownerMemberId));

        User foreignUser = userRepository.saveAndFlush(
                User.create("statistics-foreign@example.test", "Foreign"));
        Household foreignHousehold = householdRepository.saveAndFlush(
                Household.create("Foreign Household"));
        HouseholdMember foreignMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(foreignHousehold, foreignUser, HouseholdRole.OWNER));

        assertThatThrownBy(() -> statisticsService.find(
                currentHousehold,
                new StatisticsFilter(
                        LocalDate.of(2026, 8, 1),
                        LocalDate.of(2026, 8, 31),
                        null,
                        null,
                        TransactionScope.PERSONAL,
                        foreignMember.getId()
                )
        )).isInstanceOfSatisfying(ApiException.class, exception ->
                assertThat(exception.status()).isEqualTo(HttpStatus.NOT_FOUND));
    }

    private StatisticsFilter filter(LocalDate from, LocalDate to) {
        return new StatisticsFilter(from, to, null, null, null, null);
    }

    private TransactionResponse income(long amount, Long ownerId, String occurredAt) {
        return transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.INCOME,
                amount,
                TransactionScope.PERSONAL,
                ownerId,
                null,
                incomeCategoryId,
                checkingAccountId,
                null,
                null,
                Instant.parse(occurredAt),
                null,
                AdjustmentType.NORMAL,
                null
        ));
    }

    private TransactionResponse expense(
            long amount,
            Long ownerId,
            Long categoryId,
            Long accountId,
            String occurredAt
    ) {
        return transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.EXPENSE,
                amount,
                TransactionScope.PERSONAL,
                ownerId,
                ownerId,
                categoryId,
                accountId,
                null,
                null,
                Instant.parse(occurredAt),
                null,
                AdjustmentType.NORMAL,
                null
        ));
    }

    private TransactionResponse sharedExpense(
            long amount,
            Long categoryId,
            Long accountId,
            String occurredAt
    ) {
        return transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.EXPENSE,
                amount,
                TransactionScope.SHARED,
                null,
                ownerMemberId,
                categoryId,
                accountId,
                null,
                null,
                Instant.parse(occurredAt),
                null,
                AdjustmentType.NORMAL,
                null
        ));
    }

    private TransactionResponse transfer(
            long amount,
            Long sourceAccountId,
            Long destinationAccountId,
            String occurredAt,
            String memo
    ) {
        return transactionService.create(currentHousehold, new TransactionCreateRequest(
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
        ));
    }

    private Category category(String name, CategoryType type, int sortOrder) {
        return categoryRepository.saveAndFlush(Category.create(
                currentHousehold.householdId(),
                null,
                name,
                type,
                null,
                null,
                sortOrder
        ));
    }

    private Long account(
            String name,
            AccountType type,
            AccountNature nature,
            boolean savingsEnabled,
            int sortOrder
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                nature,
                AccountOwnership.SHARED,
                null,
                0L,
                LocalDate.of(2026, 1, 1),
                "KRW",
                null,
                savingsEnabled,
                sortOrder
        )).id();
    }

    private void archiveCategory(Long categoryId) {
        Category category = categoryRepository.findById(categoryId).orElseThrow();
        category.update(
                category.getGroupId(),
                category.getName(),
                category.getIconKey(),
                category.getColorKey(),
                category.getSortOrder(),
                true
        );
        categoryRepository.saveAndFlush(category);
    }

    private void archiveAccount(Long accountId) {
        Account account = accountRepository.findById(accountId).orElseThrow();
        account.update(
                account.getName(),
                account.getInstitution(),
                account.getType(),
                account.getNature(),
                account.getOwnership(),
                account.getOwnerMemberId(),
                account.getOpeningBalance(),
                account.getOpeningBalanceAsOf(),
                account.getCurrency(),
                account.getLastFour(),
                account.isSavingsEnabled(),
                account.getSortOrder(),
                true
        );
        accountRepository.saveAndFlush(account);
    }

    private void assertBadRequest(StatisticsFilter filter) {
        assertThatThrownBy(() -> statisticsService.find(currentHousehold, filter))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.status()).isEqualTo(HttpStatus.BAD_REQUEST));
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
