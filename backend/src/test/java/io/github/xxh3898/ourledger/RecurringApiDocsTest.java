package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryResponse;
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
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
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
class RecurringApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "recurring-docs-owner@example.test";

    @Autowired private MockMvc mockMvc;
    @Autowired private HouseholdBootstrapService bootstrapService;
    @Autowired private UserRepository userRepository;
    @Autowired private HouseholdRepository householdRepository;
    @Autowired private HouseholdMemberRepository householdMemberRepository;
    @Autowired private AccountService accountService;
    @Autowired private CategoryService categoryService;
    @Autowired private JdbcTemplate jdbcTemplate;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private AccountResponse account;
    private CategoryResponse category;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        bootstrapService.provision(new HouseholdBootstrapRequest(
                "Recurring Docs Household",
                OWNER_EMAIL,
                "Recurring Docs Owner",
                "recurring-docs-member@example.test",
                "Recurring Docs Member"
        ));
        User owner = userRepository.findByEmail(OWNER_EMAIL).orElseThrow();
        Household household = householdRepository.findAll().getFirst();
        ownerMemberId = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(household.getId())
                .stream()
                .filter(member -> member.getRole() == HouseholdRole.OWNER)
                .findFirst().orElseThrow().getId();
        currentHousehold = new CurrentHousehold(
                owner.getId(), owner.getEmail(), owner.getDisplayName(), household.getId(),
                household.getName(), household.getBaseCurrency(), household.getTimezone(),
                HouseholdRole.OWNER
        );
        account = accountService.create(currentHousehold, new AccountCreateRequest(
                "주거래 통장", null, AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, ownerMemberId, 0L,
                LocalDate.of(2026, 8, 1), "KRW", null, false, 0));
        category = categoryService.create(currentHousehold, new CategoryCreateRequest(
                null, "급여", CategoryType.INCOME, null, null, 0));
    }

    @AfterEach
    void removeFixtures() {
        clearDatabase();
    }

    @Test
    void should_documentRecurringCrud_when_currentHouseholdManagesRule() throws Exception {
        Cookie csrf = csrfCookie();
        String createJson = createJson(true);

        mockMvc.perform(post("/api/v1/recurring-transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createJson))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("월급"))
                .andExpect(jsonPath("$.owner.memberId").value(ownerMemberId))
                .andExpect(jsonPath("$.accounts[0].role").value("PRIMARY"))
                .andExpect(jsonPath("$.frequency").value("MONTHLY"))
                .andExpect(jsonPath("$.scheduledLocalTime").value("09:00:00"))
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andDo(document("recurring-create"));

        mockMvc.perform(get("/api/v1/recurring-transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("월급"))
                .andDo(document("recurring-list"));

        mockMvc.perform(patch("/api/v1/recurring-transactions/1")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(updateJson(0, false)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.active").value(false))
                .andExpect(jsonPath("$.status").value("PAUSED"))
                .andDo(document("recurring-update"));

        mockMvc.perform(patch("/api/v1/recurring-transactions/1")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(updateJson(0, true)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("RECURRING_VERSION_CONFLICT"))
                .andDo(document("recurring-version-conflict"));
    }

    @Test
    void should_preserveCsrfAndHouseholdBoundary_when_recurringRequestIsUnsafe()
            throws Exception {
        mockMvc.perform(post("/api/v1/recurring-transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createJson(true)))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));

        Cookie csrf = csrfCookie();
        mockMvc.perform(patch("/api/v1/recurring-transactions/999999")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(updateJson(0, true)))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));

        mockMvc.perform(post("/api/v1/recurring-transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(createJson(false)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("RECURRING_AUTO_POST_REQUIRED"))
                .andDo(document("recurring-auto-post-required"));
    }

    private Cookie csrfCookie() throws Exception {
        return mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andReturn().getResponse().getCookie("XSRF-TOKEN");
    }

    private String createJson(boolean autoPost) {
        return """
                {
                  "name": "월급",
                  "type": "INCOME",
                  "amount": 3000000,
                  "scope": "PERSONAL",
                  "ownerMemberId": %d,
                  "payerMemberId": null,
                  "categoryId": %d,
                  "accountId": %d,
                  "sourceAccountId": null,
                  "destinationAccountId": null,
                  "frequency": "MONTHLY",
                  "intervalValue": 1,
                  "startDate": "2099-09-25",
                  "endDate": null,
                  "scheduledLocalTime": "09:00",
                  "memo": "급여 자동 반영",
                  "autoPost": %s,
                  "active": true
                }
                """.formatted(ownerMemberId, category.id(), account.id(), autoPost);
    }

    private String updateJson(long version, boolean active) {
        return """
                {
                  "version": %d,
                  "name": "월급",
                  "type": "INCOME",
                  "amount": 3000000,
                  "scope": "PERSONAL",
                  "ownerMemberId": %d,
                  "payerMemberId": null,
                  "categoryId": %d,
                  "accountId": %d,
                  "sourceAccountId": null,
                  "destinationAccountId": null,
                  "frequency": "MONTHLY",
                  "intervalValue": 1,
                  "startDate": "2099-09-25",
                  "endDate": null,
                  "scheduledLocalTime": "09:00",
                  "memo": "급여 자동 반영",
                  "autoPost": true,
                  "active": %s
                }
                """.formatted(version, ownerMemberId, category.id(), account.id(), active);
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
