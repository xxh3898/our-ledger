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
import io.github.xxh3898.ourledger.goal.GoalAccountRepository;
import io.github.xxh3898.ourledger.goal.GoalRepository;
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
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import({TestcontainersConfiguration.class, AssetsApiDocsTest.FixedClockConfiguration.class})
@SpringBootTest
class AssetsApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "assets-docs-owner@example.test";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private AccountService accountService;

    @Autowired
    private GoalAccountRepository goalAccountRepository;

    @Autowired
    private GoalRepository goalRepository;

    @Autowired
    private RecurringTransactionAccountRepository recurringAccountRepository;

    @Autowired
    private RecurringTransactionRepository recurringRepository;

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
    private HouseholdMemberRepository memberRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private UserRepository userRepository;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long incomeCategoryId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        User owner = userRepository.saveAndFlush(User.create(OWNER_EMAIL, "Assets Owner"));
        User partner = userRepository.saveAndFlush(
                User.create("assets-docs-partner@example.test", "Assets Partner"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Assets Docs Household"));
        HouseholdMember ownerMember = memberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));
        memberRepository.saveAndFlush(
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
        incomeCategoryId = categoryRepository.saveAndFlush(Category.create(
                household.getId(),
                null,
                "급여",
                CategoryType.INCOME,
                null,
                null,
                0
        )).getId();
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_documentAssetsReadModel_when_currentHouseholdRequestsOverview()
            throws Exception {
        Long assetId = accountService.create(currentHousehold, new AccountCreateRequest(
                "생활 통장",
                "은행",
                AccountType.CHECKING,
                AccountNature.ASSET,
                AccountOwnership.PERSONAL,
                ownerMemberId,
                1_000L,
                LocalDate.of(2026, 1, 1),
                "KRW",
                "1234",
                false,
                0
        )).id();
        accountService.create(currentHousehold, new AccountCreateRequest(
                "공동 카드",
                null,
                AccountType.CREDIT_CARD,
                AccountNature.LIABILITY,
                AccountOwnership.SHARED,
                null,
                -200L,
                LocalDate.of(2026, 1, 1),
                "KRW",
                null,
                false,
                0
        ));
        transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.INCOME,
                3_000L,
                TransactionScope.PERSONAL,
                ownerMemberId,
                null,
                incomeCategoryId,
                assetId,
                null,
                null,
                Instant.parse("2026-08-01T03:00:00Z"),
                "월급",
                AdjustmentType.NORMAL,
                null
        ));

        mockMvc.perform(get("/api/v1/assets")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.asOf").value("2026-08-29T00:00:00Z"))
                .andExpect(jsonPath("$.timezone").value("Asia/Seoul"))
                .andExpect(jsonPath("$.household.totalAssets").value(4_000))
                .andExpect(jsonPath("$.household.totalLiabilities").value(-200))
                .andExpect(jsonPath("$.household.netWorth").value(4_200))
                .andExpect(jsonPath("$.members.length()").value(2))
                .andExpect(jsonPath("$.members[0].displayName").value("Assets Owner"))
                .andExpect(jsonPath("$.shared.totalLiabilities").value(-200))
                .andExpect(jsonPath("$.accounts.length()").value(2))
                .andExpect(jsonPath("$.accounts[0].ledgerDelta").value(3_000))
                .andExpect(jsonPath("$.accounts[0].lastFour").doesNotExist())
                .andExpect(jsonPath("$.monthlyTrend.length()").value(12))
                .andExpect(jsonPath("$.monthlyTrend[11].month").value("2026-08"))
                .andExpect(jsonPath("$.monthlyTrend[11].complete").value(false))
                .andExpect(jsonPath("$.monthlyTrend[11].netWorth").value(4_200))
                .andDo(document("assets-read-model"));
    }

    @Test
    void should_requireAuthentication_when_assetsOverviewIsRequested() throws Exception {
        mockMvc.perform(get("/api/v1/assets"))
                .andExpect(status().isUnauthorized())
                .andDo(document("assets-authentication-required"));
    }

    private void clearDatabase() {
        goalAccountRepository.deleteAllInBatch();
        goalRepository.deleteAllInBatch();
        recurringAccountRepository.deleteAllInBatch();
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        recurringRepository.deleteAllInBatch();
        budgetRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        categoryGroupRepository.deleteAllInBatch();
        accountRepository.deleteAllInBatch();
        memberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedAssetsClock() {
            return Clock.fixed(
                    Instant.parse("2026-08-29T00:00:00Z"),
                    ZoneOffset.UTC
            );
        }
    }
}
