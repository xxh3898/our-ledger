package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.budget.BudgetCreateRequest;
import io.github.xxh3898.ourledger.budget.BudgetMonthResponse;
import io.github.xxh3898.ourledger.budget.BudgetRepository;
import io.github.xxh3898.ourledger.budget.BudgetResponse;
import io.github.xxh3898.ourledger.budget.BudgetScope;
import io.github.xxh3898.ourledger.budget.BudgetService;
import io.github.xxh3898.ourledger.budget.BudgetUpdateRequest;
import io.github.xxh3898.ourledger.category.Category;
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
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
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

import java.time.Instant;
import java.time.LocalDate;
import java.time.YearMonth;
import java.util.Objects;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class BudgetIntegrationTest {

    @Autowired
    private BudgetService budgetService;

    @Autowired
    private AccountService accountService;

    @Autowired
    private AccountRepository accountRepository;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private BudgetRepository budgetRepository;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private UserRepository userRepository;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long partnerMemberId;
    private Long expenseCategoryId;
    private Long sharedCategoryId;
    private Long incomeCategoryId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        User owner = userRepository.saveAndFlush(
                User.create("budget-owner@example.test", "Owner"));
        User partner = userRepository.saveAndFlush(
                User.create("budget-partner@example.test", "Partner"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Budget Household"));
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
        expenseCategoryId = createCategory(household.getId(), "식비", CategoryType.EXPENSE, 0)
                .getId();
        sharedCategoryId = createCategory(household.getId(), "데이트", CategoryType.EXPENSE, 1)
                .getId();
        incomeCategoryId = createCategory(household.getId(), "급여", CategoryType.INCOME, 0)
                .getId();
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_calculateScopeAndCategoryBudgets_when_monthContainsLedgerVariants() {
        LedgerTransaction original = saveTransaction(
                TransactionType.EXPENSE, 50_000, TransactionScope.PERSONAL,
                ownerMemberId, expenseCategoryId, "2026-08-10T03:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.EXPENSE, 10_000, TransactionScope.PERSONAL,
                ownerMemberId, expenseCategoryId, "2026-08-11T03:00:00Z",
                AdjustmentType.REFUND, original.getId());
        saveTransaction(
                TransactionType.EXPENSE, 30_000, TransactionScope.PERSONAL,
                partnerMemberId, expenseCategoryId, "2026-08-12T03:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.EXPENSE, 20_000, TransactionScope.SHARED,
                null, sharedCategoryId, "2026-08-13T03:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.EXPENSE, 5_000, TransactionScope.PERSONAL,
                ownerMemberId, expenseCategoryId, "2026-07-31T15:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.EXPENSE, 7_000, TransactionScope.PERSONAL,
                ownerMemberId, expenseCategoryId, "2026-08-31T15:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.EXPENSE, 15_000, TransactionScope.PERSONAL,
                ownerMemberId, expenseCategoryId, "2026-08-20T03:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.INCOME, 999_000, TransactionScope.PERSONAL,
                ownerMemberId, incomeCategoryId, "2026-08-20T04:00:00Z",
                AdjustmentType.NORMAL, null);
        saveTransaction(
                TransactionType.TRANSFER, 15_000, null,
                null, null, "2026-08-20T05:00:00Z",
                AdjustmentType.NORMAL, null);
        LedgerTransaction deleted = saveTransaction(
                TransactionType.EXPENSE, 500_000, TransactionScope.SHARED,
                null, sharedCategoryId, "2026-08-21T03:00:00Z",
                AdjustmentType.NORMAL, null);
        deleted.delete(ownerMemberId);
        transactionRepository.saveAndFlush(deleted);

        createBudget(BudgetScope.HOUSEHOLD, null, null, 100_000);
        createBudget(BudgetScope.PERSONAL, ownerMemberId, null, 0);
        createBudget(BudgetScope.SHARED, null, null, 30_000);
        createBudget(BudgetScope.HOUSEHOLD, null, expenseCategoryId, 100_000);
        createBudget(BudgetScope.SHARED, null, sharedCategoryId, 0);

        BudgetMonthResponse response = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));

        assertThat(response.month()).isEqualTo(YearMonth.of(2026, 8));
        assertThat(response.timezone()).isEqualTo("Asia/Seoul");
        assertThat(response.scopes()).hasSize(4);
        assertScope(response, BudgetScope.HOUSEHOLD, null, 100_000L, 110_000L, -10_000L, true);
        assertScope(response, BudgetScope.PERSONAL, ownerMemberId, 0L, 60_000L, -60_000L, true);
        assertScope(response, BudgetScope.PERSONAL, partnerMemberId, null, 30_000L, null, false);
        assertScope(response, BudgetScope.SHARED, null, 30_000L, 20_000L, 10_000L, false);

        assertThat(response.categories()).hasSize(2);
        BudgetMonthResponse.CategoryBudget food = response.categories().stream()
                .filter(item -> item.category().id().equals(expenseCategoryId))
                .findFirst()
                .orElseThrow();
        assertThat(food)
                .extracting(
                        BudgetMonthResponse.CategoryBudget::budgetAmount,
                        BudgetMonthResponse.CategoryBudget::spentAmount,
                        BudgetMonthResponse.CategoryBudget::remainingAmount,
                        BudgetMonthResponse.CategoryBudget::exceeded
                )
                .containsExactly(100_000L, 90_000L, 10_000L, false);
        BudgetMonthResponse.CategoryBudget shared = response.categories().stream()
                .filter(item -> item.category().id().equals(sharedCategoryId))
                .findFirst()
                .orElseThrow();
        assertThat(shared)
                .extracting(
                        BudgetMonthResponse.CategoryBudget::budgetAmount,
                        BudgetMonthResponse.CategoryBudget::spentAmount,
                        BudgetMonthResponse.CategoryBudget::remainingAmount,
                        BudgetMonthResponse.CategoryBudget::exceeded
                )
                .containsExactly(0L, 20_000L, -20_000L, true);
    }

    @Test
    void should_preserveSpendingAndVersionContract_when_budgetIsUpdatedAndDeleted() {
        saveTransaction(
                TransactionType.EXPENSE, 12_000, TransactionScope.SHARED,
                null, sharedCategoryId, "2026-08-10T03:00:00Z",
                AdjustmentType.NORMAL, null);
        BudgetResponse created = createBudget(BudgetScope.HOUSEHOLD, null, null, 0);

        BudgetResponse updated = budgetService.update(
                currentHousehold,
                created.id(),
                new BudgetUpdateRequest(
                        created.version(),
                        YearMonth.of(2026, 8),
                        BudgetScope.SHARED,
                        null,
                        null,
                        20_000L
                )
        );

        assertThat(updated.version()).isEqualTo(created.version() + 1);
        assertThat(updated.scope()).isEqualTo(BudgetScope.SHARED);
        assertThatThrownBy(() -> budgetService.update(
                currentHousehold,
                updated.id(),
                new BudgetUpdateRequest(
                        created.version(),
                        YearMonth.of(2026, 8),
                        BudgetScope.SHARED,
                        null,
                        null,
                        30_000L
                )
        )).isInstanceOfSatisfying(ApiException.class, exception ->
                assertThat(exception.code()).isEqualTo(ApiErrorCode.BUDGET_VERSION_CONFLICT));
        assertThatThrownBy(() -> budgetService.delete(
                currentHousehold, updated.id(), created.version()))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code())
                                .isEqualTo(ApiErrorCode.BUDGET_VERSION_CONFLICT));

        budgetService.delete(currentHousehold, updated.id(), updated.version());
        BudgetMonthResponse response = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));
        BudgetMonthResponse.ScopeBudget shared = response.scopes().stream()
                .filter(item -> item.scope() == BudgetScope.SHARED)
                .findFirst()
                .orElseThrow();
        assertThat(shared.budgetAmount()).isNull();
        assertThat(shared.spentAmount()).isEqualTo(12_000);
        assertThat(shared.remainingAmount()).isNull();
    }

    @Test
    void should_includeCardPurchaseAndAllowOverrun_when_cardPaymentIsTransfer() {
        AccountResponse checking = accountService.create(
                currentHousehold,
                new AccountCreateRequest(
                        "생활비 통장",
                        null,
                        AccountType.CHECKING,
                        AccountNature.ASSET,
                        AccountOwnership.PERSONAL,
                        ownerMemberId,
                        100_000L,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        null,
                        false,
                        0
                )
        );
        AccountResponse card = accountService.create(
                currentHousehold,
                new AccountCreateRequest(
                        "생활 신용카드",
                        null,
                        AccountType.CREDIT_CARD,
                        AccountNature.LIABILITY,
                        AccountOwnership.PERSONAL,
                        ownerMemberId,
                        0L,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        null,
                        false,
                        1
                )
        );
        createBudget(BudgetScope.SHARED, null, null, 0);

        transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.EXPENSE,
                12_000L,
                TransactionScope.SHARED,
                null,
                null,
                sharedCategoryId,
                card.id(),
                null,
                null,
                Instant.parse("2026-08-15T03:00:00Z"),
                "카드 지출",
                AdjustmentType.NORMAL,
                null
        ));
        transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.TRANSFER,
                12_000L,
                null,
                null,
                null,
                null,
                null,
                checking.id(),
                card.id(),
                Instant.parse("2026-08-25T03:00:00Z"),
                "카드대금 납부",
                AdjustmentType.NORMAL,
                null
        ));

        BudgetMonthResponse response = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));

        assertScope(response, BudgetScope.HOUSEHOLD, null, null, 12_000L, null, false);
        assertScope(response, BudgetScope.SHARED, null, 0L, 12_000L, -12_000L, true);
    }

    @Test
    void should_keepArchivedCategoryBudget_when_categoryIsArchivedAfterCreation() {
        BudgetResponse created = createBudget(
                BudgetScope.PERSONAL,
                ownerMemberId,
                expenseCategoryId,
                25_000
        );
        Category category = categoryRepository.findById(expenseCategoryId).orElseThrow();
        category.update(null, category.getName(), null, null, category.getSortOrder(), true);
        categoryRepository.saveAndFlush(category);

        BudgetMonthResponse response = budgetService.findMonth(
                currentHousehold, YearMonth.of(2026, 8));

        assertThat(response.categories()).singleElement().satisfies(budget -> {
            assertThat(budget.budgetId()).isEqualTo(created.id());
            assertThat(budget.category().id()).isEqualTo(expenseCategoryId);
            assertThat(budget.category().archived()).isTrue();
        });
    }

    @Test
    void should_rejectInvalidReferencesDuplicatesAndArchivedCategory_when_budgetMutates() {
        assertApiError(
                () -> createBudget(BudgetScope.PERSONAL, null, null, 10_000),
                HttpStatus.BAD_REQUEST,
                ApiErrorCode.INVALID_REQUEST
        );
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, ownerMemberId, null, 10_000),
                HttpStatus.BAD_REQUEST,
                ApiErrorCode.INVALID_REQUEST
        );
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, null, null, -1),
                HttpStatus.BAD_REQUEST,
                ApiErrorCode.INVALID_REQUEST
        );
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, null, incomeCategoryId, 10_000),
                HttpStatus.UNPROCESSABLE_ENTITY,
                ApiErrorCode.CATEGORY_TYPE_MISMATCH
        );

        Category archived = categoryRepository.findById(expenseCategoryId).orElseThrow();
        archived.update(null, archived.getName(), null, null, archived.getSortOrder(), true);
        categoryRepository.saveAndFlush(archived);
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, null, expenseCategoryId, 10_000),
                HttpStatus.UNPROCESSABLE_ENTITY,
                ApiErrorCode.ARCHIVED_CATEGORY_NOT_ALLOWED
        );

        BudgetResponse first = createBudget(BudgetScope.HOUSEHOLD, null, null, 10_000);
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, null, null, 20_000),
                HttpStatus.CONFLICT,
                ApiErrorCode.BUDGET_DUPLICATE
        );
        BudgetResponse shared = createBudget(BudgetScope.SHARED, null, null, 30_000);
        assertApiError(
                () -> budgetService.update(
                        currentHousehold,
                        shared.id(),
                        new BudgetUpdateRequest(
                                shared.version(),
                                YearMonth.of(2026, 8),
                                BudgetScope.HOUSEHOLD,
                                null,
                                null,
                                30_000L
                        )
                ),
                HttpStatus.CONFLICT,
                ApiErrorCode.BUDGET_DUPLICATE
        );
        assertThat(first.id()).isNotEqualTo(shared.id());

        ForeignFixture foreign = createForeignFixture();
        assertApiError(
                () -> createBudget(BudgetScope.PERSONAL, foreign.memberId(), null, 10_000),
                HttpStatus.NOT_FOUND,
                ApiErrorCode.RESOURCE_NOT_FOUND
        );
        assertApiError(
                () -> createBudget(BudgetScope.HOUSEHOLD, null, foreign.categoryId(), 10_000),
                HttpStatus.NOT_FOUND,
                ApiErrorCode.RESOURCE_NOT_FOUND
        );
        assertApiError(
                () -> budgetService.delete(currentHousehold, foreign.budgetId(), 0L),
                HttpStatus.NOT_FOUND,
                ApiErrorCode.RESOURCE_NOT_FOUND
        );
    }

    private BudgetResponse createBudget(
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        return budgetService.create(currentHousehold, new BudgetCreateRequest(
                YearMonth.of(2026, 8),
                scope,
                ownerMemberId,
                categoryId,
                amount
        ));
    }

    private void assertScope(
            BudgetMonthResponse response,
            BudgetScope scope,
            Long ownerMemberId,
            Long budgetAmount,
            long spentAmount,
            Long remainingAmount,
            boolean exceeded
    ) {
        BudgetMonthResponse.ScopeBudget item = response.scopes().stream()
                .filter(candidate -> candidate.scope() == scope)
                .filter(candidate -> Objects.equals(
                        candidate.owner() == null ? null : candidate.owner().memberId(),
                        ownerMemberId
                ))
                .findFirst()
                .orElseThrow();
        assertThat(item.budgetAmount()).isEqualTo(budgetAmount);
        assertThat(item.spentAmount()).isEqualTo(spentAmount);
        assertThat(item.remainingAmount()).isEqualTo(remainingAmount);
        assertThat(item.exceeded()).isEqualTo(exceeded);
    }

    private LedgerTransaction saveTransaction(
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long categoryId,
            String occurredAt,
            AdjustmentType adjustmentType,
            Long reversesTransactionId
    ) {
        return transactionRepository.saveAndFlush(LedgerTransaction.create(
                currentHousehold.householdId(),
                type,
                amount,
                scope,
                ownerMemberId,
                null,
                categoryId,
                Instant.parse(occurredAt),
                null,
                adjustmentType,
                reversesTransactionId,
                ownerMemberId == null ? this.ownerMemberId : ownerMemberId
        ));
    }

    private Category createCategory(
            Long householdId,
            String name,
            CategoryType type,
            int sortOrder
    ) {
        return categoryRepository.saveAndFlush(Category.create(
                householdId, null, name, type, null, null, sortOrder));
    }

    private ForeignFixture createForeignFixture() {
        User foreignUser = userRepository.saveAndFlush(
                User.create("budget-foreign@example.test", "Foreign"));
        Household foreignHousehold = householdRepository.saveAndFlush(
                Household.create("Foreign Budget Household"));
        HouseholdMember foreignMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(foreignHousehold, foreignUser, HouseholdRole.OWNER));
        Category foreignCategory = createCategory(
                foreignHousehold.getId(), "외부 식비", CategoryType.EXPENSE, 0);
        Long foreignBudgetId = budgetRepository.saveAndFlush(
                io.github.xxh3898.ourledger.budget.Budget.create(
                        foreignHousehold.getId(),
                        YearMonth.of(2026, 8).atDay(1),
                        BudgetScope.HOUSEHOLD,
                        null,
                        null,
                        10_000
                )).getId();
        return new ForeignFixture(
                foreignMember.getId(), foreignCategory.getId(), foreignBudgetId);
    }

    private void assertApiError(
            Runnable action,
            HttpStatus status,
            ApiErrorCode code
    ) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.status()).isEqualTo(status);
                    assertThat(exception.code()).isEqualTo(code);
                });
    }

    private void clearDatabase() {
        budgetRepository.deleteAllInBatch();
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    private record ForeignFixture(Long memberId, Long categoryId, Long budgetId) {
    }
}
