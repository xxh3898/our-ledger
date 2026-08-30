package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.budget.BudgetCreateRequest;
import io.github.xxh3898.ourledger.budget.BudgetRepository;
import io.github.xxh3898.ourledger.budget.BudgetResponse;
import io.github.xxh3898.ourledger.budget.BudgetScope;
import io.github.xxh3898.ourledger.budget.BudgetService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.YearMonth;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class BudgetApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "budget-docs-owner@example.test";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private HouseholdBootstrapService householdBootstrapService;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private CategoryGroupRepository categoryGroupRepository;

    @Autowired
    private CategoryService categoryService;

    @Autowired
    private BudgetRepository budgetRepository;

    @Autowired
    private BudgetService budgetService;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long expenseCategoryId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Budget Docs Household",
                OWNER_EMAIL,
                "Budget Owner",
                "budget-docs-member@example.test",
                "Budget Member"
        ));
        User owner = userRepository.findByEmail(OWNER_EMAIL).orElseThrow();
        Household household = householdRepository.findAll().getFirst();
        ownerMemberId = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(household.getId())
                .stream()
                .filter(member -> member.getRole() == HouseholdRole.OWNER)
                .findFirst()
                .orElseThrow()
                .getId();
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
        categoryService.create(currentHousehold, new CategoryCreateRequest(
                null, "식비", CategoryType.EXPENSE, null, null, 0));
        expenseCategoryId = categoryRepository.findAll().getFirst().getId();
    }

    @AfterEach
    void removeFixtures() {
        clearDatabase();
    }

    @Test
    void should_documentBudgetCrudAndMonthReadModel_when_currentHouseholdMutatesBudget()
            throws Exception {
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/budgets")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "month": "2026-08",
                                  "scope": "HOUSEHOLD",
                                  "ownerMemberId": null,
                                  "categoryId": null,
                                  "amount": 1500000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.month").value("2026-08"))
                .andExpect(jsonPath("$.scope").value("HOUSEHOLD"))
                .andExpect(jsonPath("$.amount").value(1_500_000))
                .andDo(document("budget-create"));

        BudgetResponse categoryBudget = budgetService.create(
                currentHousehold,
                new BudgetCreateRequest(
                        YearMonth.of(2026, 8),
                        BudgetScope.PERSONAL,
                        ownerMemberId,
                        expenseCategoryId,
                        300_000L
                )
        );
        mockMvc.perform(get("/api/v1/budgets")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .queryParam("month", "2026-08"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.timezone").value("Asia/Seoul"))
                .andExpect(jsonPath("$.scopes.length()").value(4))
                .andExpect(jsonPath("$.categories[0].budgetId").value(categoryBudget.id()))
                .andExpect(jsonPath("$.categories[0].owner.memberId").value(ownerMemberId))
                .andExpect(jsonPath("$.categories[0].category.id").value(expenseCategoryId))
                .andDo(document("budget-month"));

        BudgetResponse householdBudget = budgetRepository.findAll().stream()
                .filter(budget -> budget.getCategoryId() == null)
                .findFirst()
                .map(budget -> new BudgetResponse(
                        budget.getId(),
                        YearMonth.from(budget.getBudgetMonth()),
                        budget.getScope(),
                        null,
                        null,
                        budget.getAmount(),
                        budget.getVersion(),
                        budget.getCreatedAt(),
                        budget.getUpdatedAt()
                ))
                .orElseThrow();
        mockMvc.perform(patch("/api/v1/budgets/{budgetId}", householdBudget.id())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "version": 0,
                                  "month": "2026-08",
                                  "scope": "HOUSEHOLD",
                                  "ownerMemberId": null,
                                  "categoryId": null,
                                  "amount": 1600000
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value(1))
                .andExpect(jsonPath("$.amount").value(1_600_000))
                .andDo(document("budget-update"));

        mockMvc.perform(patch("/api/v1/budgets/{budgetId}", householdBudget.id())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "version": 0,
                                  "month": "2026-08",
                                  "scope": "HOUSEHOLD",
                                  "ownerMemberId": null,
                                  "categoryId": null,
                                  "amount": 1700000
                                }
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("BUDGET_VERSION_CONFLICT"))
                .andDo(document("budget-version-conflict"));

        mockMvc.perform(delete("/api/v1/budgets/{budgetId}", householdBudget.id())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .queryParam("version", "1"))
                .andExpect(status().isNoContent())
                .andDo(document("budget-delete"));
    }

    @Test
    void should_preserveCsrfAndDuplicateErrors_when_budgetRequestIsUnsafe() throws Exception {
        mockMvc.perform(post("/api/v1/budgets")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "month": "2026-08",
                                  "scope": "HOUSEHOLD",
                                  "ownerMemberId": null,
                                  "categoryId": null,
                                  "amount": 100000
                                }
                                """))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));

        budgetService.create(currentHousehold, new BudgetCreateRequest(
                YearMonth.of(2026, 8), BudgetScope.HOUSEHOLD, null, null, 100_000L));
        Cookie csrf = csrfCookie();
        mockMvc.perform(post("/api/v1/budgets")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "month": "2026-08",
                                  "scope": "HOUSEHOLD",
                                  "ownerMemberId": null,
                                  "categoryId": null,
                                  "amount": 200000
                                }
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("BUDGET_DUPLICATE"))
                .andDo(document("budget-duplicate"));
    }

    private Cookie csrfCookie() throws Exception {
        return mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getCookie("XSRF-TOKEN");
    }

    private void clearDatabase() {
        budgetRepository.deleteAllInBatch();
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        categoryGroupRepository.deleteAllInBatch();
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }
}
