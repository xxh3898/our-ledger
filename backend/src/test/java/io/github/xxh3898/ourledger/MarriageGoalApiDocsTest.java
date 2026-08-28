package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.goal.GoalAccountRepository;
import io.github.xxh3898.ourledger.goal.GoalRepository;
import io.github.xxh3898.ourledger.goal.MarriageGoalCreateRequest;
import io.github.xxh3898.ourledger.goal.MarriageGoalService;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionAccountRepository;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionRepository;
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

import java.time.LocalDate;

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
class MarriageGoalApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "goal-docs-owner@example.test";

    @Autowired private MockMvc mockMvc;
    @Autowired private HouseholdBootstrapService householdBootstrapService;
    @Autowired private UserRepository userRepository;
    @Autowired private HouseholdRepository householdRepository;
    @Autowired private HouseholdMemberRepository householdMemberRepository;
    @Autowired private AccountService accountService;
    @Autowired private AccountRepository accountRepository;
    @Autowired private MarriageGoalService goalService;
    @Autowired private GoalAccountRepository goalAccountRepository;
    @Autowired private GoalRepository goalRepository;
    @Autowired private RecurringTransactionAccountRepository recurringAccountRepository;
    @Autowired private RecurringTransactionRepository recurringRepository;
    @Autowired private TransactionAccountEntryRepository entryRepository;
    @Autowired private LedgerTransactionRepository transactionRepository;
    @Autowired private CategoryRepository categoryRepository;
    @Autowired private CategoryGroupRepository categoryGroupRepository;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private AccountResponse savingsAccount;

    @BeforeEach
    void setUp() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Goal Docs Household",
                OWNER_EMAIL,
                "Goal Owner",
                "goal-docs-member@example.test",
                "Goal Member"
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
                owner.getId(), owner.getEmail(), owner.getDisplayName(),
                household.getId(), household.getName(), household.getBaseCurrency(),
                household.getTimezone(), HouseholdRole.OWNER
        );
        savingsAccount = accountService.create(
                currentHousehold,
                new AccountCreateRequest(
                        "결혼 적금", null, AccountType.SAVINGS, AccountNature.ASSET,
                        AccountOwnership.PERSONAL, ownerMemberId, 5_000_000L,
                        LocalDate.of(2026, 8, 1), "KRW", null, true, 0
                )
        );
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_documentMarriageGoalReadCreateUpdateLinkAndUnlink() throws Exception {
        mockMvc.perform(get("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.goal").doesNotExist())
                .andExpect(jsonPath("$.eligibleAccounts[0].id").value(savingsAccount.id()))
                .andDo(document("marriage-goal-empty"));

        Cookie csrf = csrfCookie();
        mockMvc.perform(post("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "우리 집까지",
                                  "targetAmount": 100000000
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.goal.name").value("우리 집까지"))
                .andExpect(jsonPath("$.goal.currentAmount").value(0))
                .andExpect(jsonPath("$.goal.projectionStatus")
                        .value("INSUFFICIENT_HISTORY"))
                .andDo(document("marriage-goal-create"));

        mockMvc.perform(post("/api/v1/goals/marriage/accounts/{accountId}", savingsAccount.id())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.goal.currentAmount").value(5_000_000))
                .andExpect(jsonPath("$.goal.linkedAccounts[0].startingBalance")
                        .value(5_000_000))
                .andDo(document("marriage-goal-account-link"));

        mockMvc.perform(patch("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "version": 0,
                                  "name": "우리 보금자리",
                                  "targetAmount": 120000000
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.goal.version").value(1))
                .andExpect(jsonPath("$.goal.targetAmount").value(120_000_000))
                .andDo(document("marriage-goal-update"));

        mockMvc.perform(get("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.goal.monthlyTrend.length()").value(6))
                .andExpect(jsonPath("$.goal.linkedAccounts[0].id")
                        .value(savingsAccount.id()))
                .andDo(document("marriage-goal-read"));

        mockMvc.perform(delete(
                        "/api/v1/goals/marriage/accounts/{accountId}", savingsAccount.id())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf))
                .andExpect(status().isNoContent())
                .andDo(document("marriage-goal-account-unlink"));
    }

    @Test
    void should_documentGoalBusinessErrorsAndPreserveCsrf() throws Exception {
        mockMvc.perform(post("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"CSRF 목표","targetAmount":1000000}
                                """))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));

        goalService.create(
                currentHousehold,
                new MarriageGoalCreateRequest("기존 목표", 10_000_000L)
        );
        Cookie csrf = csrfCookie();
        mockMvc.perform(post("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"중복 목표","targetAmount":20000000}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("GOAL_ALREADY_EXISTS"))
                .andDo(document("marriage-goal-duplicate"));

        mockMvc.perform(patch("/api/v1/goals/marriage")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"version":9,"name":"stale","targetAmount":20000000}
                                """))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("GOAL_VERSION_CONFLICT"))
                .andDo(document("marriage-goal-version-conflict"));
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
        goalAccountRepository.deleteAllInBatch();
        goalRepository.deleteAllInBatch();
        recurringAccountRepository.deleteAllInBatch();
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        recurringRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        categoryGroupRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }
}
