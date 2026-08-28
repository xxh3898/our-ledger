package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
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
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
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
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.time.LocalDate;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class StatisticsApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "statistics-docs-owner@example.test";

    @Autowired
    private MockMvc mockMvc;

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
    private Long incomeCategoryId;
    private Long expenseCategoryId;
    private Long checkingAccountId;
    private Long savingsAccountId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        User owner = userRepository.saveAndFlush(User.create(OWNER_EMAIL, "Statistics Owner"));
        User partner = userRepository.saveAndFlush(
                User.create("statistics-docs-partner@example.test", "Statistics Partner"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Statistics Docs Household"));
        HouseholdMember ownerMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, partner, HouseholdRole.MEMBER));
        ownerMemberId = ownerMember.getId();
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
        incomeCategoryId = category("급여", CategoryType.INCOME, 0);
        expenseCategoryId = category("식비", CategoryType.EXPENSE, 1);
        checkingAccountId = account("생활비", AccountType.CHECKING, false, 0);
        savingsAccountId = account("결혼 적금", AccountType.SAVINGS, true, 1);
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_documentStatisticsReadModels_when_currentHouseholdRequestsPeriod() throws Exception {
        transactionService.create(currentHousehold, request(
                TransactionType.INCOME,
                3_000_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                incomeCategoryId,
                checkingAccountId,
                null,
                null,
                "2026-08-01T03:00:00Z",
                "월급"
        ));
        transactionService.create(currentHousehold, request(
                TransactionType.EXPENSE,
                120_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                expenseCategoryId,
                checkingAccountId,
                null,
                null,
                "2026-08-02T03:00:00Z",
                "장보기"
        ));
        transactionService.create(currentHousehold, request(
                TransactionType.TRANSFER,
                1_000_000,
                null,
                null,
                null,
                null,
                checkingAccountId,
                savingsAccountId,
                "2026-08-03T03:00:00Z",
                "결혼자금"
        ));

        mockMvc.perform(get("/api/v1/statistics")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31")
                        .queryParam("compareFrom", "2026-07-01")
                        .queryParam("compareTo", "2026-07-31"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.period.timezone").value("Asia/Seoul"))
                .andExpect(jsonPath("$.summary.incomeAmount").value(3_000_000))
                .andExpect(jsonPath("$.summary.netSpendingAmount").value(120_000))
                .andExpect(jsonPath("$.summary.savingsAmount").value(1_000_000))
                .andExpect(jsonPath("$.summary.savingsRate").value(33.3))
                .andExpect(jsonPath("$.comparison.incomePercentChange").doesNotExist())
                .andExpect(jsonPath("$.subjects.length()").value(3))
                .andExpect(jsonPath("$.categories[0].category.name").value("식비"))
                .andExpect(jsonPath("$.accounts[0].account.name").value("생활비"))
                .andExpect(jsonPath("$.months[0].month").value("2026-08"))
                .andDo(document("statistics-read-model"));

        mockMvc.perform(get("/api/v1/statistics/savings-activities")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].savingsImpactAmount").value(1_000_000))
                .andExpect(jsonPath("$[0].sourceAccount.name").value("생활비"))
                .andExpect(jsonPath("$[0].destinationAccount.name").value("결혼 적금"))
                .andDo(document("statistics-savings-activities"));
    }

    @Test
    void should_preserveAuthenticationAndValidationErrors_when_statisticsRequestIsInvalid()
            throws Exception {
        mockMvc.perform(get("/api/v1/statistics")
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/v1/statistics")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .queryParam("to", "2026-08-31"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andDo(document("statistics-invalid-request"));

        mockMvc.perform(get("/api/v1/statistics")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .queryParam("from", "2026-08-01")
                        .queryParam("to", "2026-08-31")
                        .queryParam("scope", "PERSONAL"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    private TransactionCreateRequest request(
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId,
            String occurredAt,
            String memo
    ) {
        return new TransactionCreateRequest(
                type,
                amount,
                scope,
                ownerId,
                type == TransactionType.EXPENSE ? ownerId : null,
                categoryId,
                accountId,
                sourceAccountId,
                destinationAccountId,
                Instant.parse(occurredAt),
                memo,
                AdjustmentType.NORMAL,
                null
        );
    }

    private Long category(String name, CategoryType type, int sortOrder) {
        return categoryRepository.saveAndFlush(Category.create(
                currentHousehold.householdId(),
                null,
                name,
                type,
                null,
                null,
                sortOrder
        )).getId();
    }

    private Long account(String name, AccountType type, boolean savings, int sortOrder) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                AccountNature.ASSET,
                AccountOwnership.SHARED,
                null,
                0L,
                LocalDate.of(2026, 1, 1),
                "KRW",
                null,
                savings,
                sortOrder
        )).id();
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
