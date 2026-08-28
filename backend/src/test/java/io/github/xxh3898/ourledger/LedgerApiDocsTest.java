package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroup;
import io.github.xxh3898.ourledger.category.CategoryGroupCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryGroupService;
import io.github.xxh3898.ourledger.category.CategoryGroupUpdateRequest;
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
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
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

import java.time.Instant;
import java.time.LocalDate;

import static org.assertj.core.api.Assertions.assertThat;
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
class LedgerApiDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;
    private static final String OWNER_EMAIL = "ledger-owner@example.test";

    @Autowired
    private MockMvc mockMvc;

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
    private CategoryGroupService categoryGroupService;

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

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long partnerMemberId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Ledger Household",
                OWNER_EMAIL,
                "Ledger Owner",
                "ledger-member@example.test",
                "Ledger Member"
        ));
        User owner = userRepository.findByEmail(OWNER_EMAIL).orElseThrow();
        Household household = householdRepository.findAll().getFirst();
        var members = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(household.getId());
        ownerMemberId = members.stream()
                .filter(member -> member.getRole() == HouseholdRole.OWNER)
                .findFirst()
                .orElseThrow()
                .getId();
        partnerMemberId = members.stream()
                .filter(member -> member.getRole() == HouseholdRole.MEMBER)
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
    }

    @AfterEach
    void removeFixtures() {
        clearDatabase();
    }

    @Test
    void should_documentAccountAndCategoryContracts_when_currentHouseholdMutatesReferences()
            throws Exception {
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/accounts")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "주거래 통장",
                                  "institution": "우리은행",
                                  "type": "CHECKING",
                                  "nature": "ASSET",
                                  "ownership": "PERSONAL",
                                  "ownerMemberId": %d,
                                  "openingBalance": 1000,
                                  "openingBalanceAsOf": "2026-08-01",
                                  "currency": "KRW",
                                  "lastFour": "1234",
                                  "savingsEnabled": false,
                                  "sortOrder": 0
                                }
                                """.formatted(ownerMemberId)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("주거래 통장"))
                .andExpect(jsonPath("$.owner.memberId").value(ownerMemberId))
                .andExpect(jsonPath("$.currentBalance").value(1000))
                .andDo(document("ledger-account-create"));

        Account account = accountRepository.findAll().getFirst();
        mockMvc.perform(patch("/api/v1/accounts/{accountId}", account.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "생활비 통장",
                                  "institution": "우리은행",
                                  "type": "CHECKING",
                                  "nature": "ASSET",
                                  "ownership": "PERSONAL",
                                  "ownerMemberId": %d,
                                  "openingBalance": 2000,
                                  "openingBalanceAsOf": "2026-08-01",
                                  "currency": "KRW",
                                  "lastFour": "1234",
                                  "savingsEnabled": false,
                                  "sortOrder": 1,
                                  "archived": true
                                }
                                """.formatted(ownerMemberId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("생활비 통장"))
                .andExpect(jsonPath("$.archived").value(true))
                .andDo(document("ledger-account-update"));

        mockMvc.perform(get("/api/v1/accounts")
                        .queryParam("includeArchived", "true")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(account.getId()))
                .andDo(document("ledger-account-list"));

        mockMvc.perform(post("/api/v1/category-groups")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"name":"생활","type":"EXPENSE","sortOrder":0}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.type").value("EXPENSE"))
                .andDo(document("ledger-category-group-create"));

        CategoryGroup group = categoryGroupRepository.findAll().getFirst();
        mockMvc.perform(post("/api/v1/categories")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "groupId": %d,
                                  "name": "식비",
                                  "type": "EXPENSE",
                                  "iconKey": "meal",
                                  "colorKey": "warm",
                                  "sortOrder": 0
                                }
                                """.formatted(group.getId())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.group.id").value(group.getId()))
                .andDo(document("ledger-category-create"));

        Category category = categoryRepository.findAll().getFirst();
        mockMvc.perform(patch("/api/v1/categories/{categoryId}", category.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "groupId": null,
                                  "name": "외식",
                                  "iconKey": null,
                                  "colorKey": null,
                                  "sortOrder": 1,
                                  "archived": false
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("외식"))
                .andExpect(jsonPath("$.group").isEmpty())
                .andDo(document("ledger-category-update"));

        mockMvc.perform(get("/api/v1/categories")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].name").value("외식"))
                .andDo(document("ledger-category-list"));
    }

    @Test
    void should_documentTransactionLifecycle_when_incomeAndExpenseChangeAccountBalance()
            throws Exception {
        AccountResponse account = createAccount(1000);
        Category incomeCategory = createCategory(CategoryType.INCOME, "급여");
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "식비");
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "INCOME", 100_000, "PERSONAL", ownerMemberId, null,
                                incomeCategory.getId(), account.id(), "2026-08-27T01:00:00Z", "급여"
                        )))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.entries[0].role").value("PRIMARY"))
                .andExpect(jsonPath("$.entries[0].balanceDelta").value(100_000))
                .andExpect(jsonPath("$.entries[0].account.id").value(account.id()))
                .andExpect(jsonPath("$.account").doesNotExist())
                .andExpect(jsonPath("$.entry").doesNotExist())
                .andExpect(jsonPath("$.version").value(0))
                .andDo(document("ledger-transaction-create"));

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 12_000, "SHARED", null, partnerMemberId,
                                expenseCategory.getId(), account.id(), "2026-08-27T02:00:00Z", "점심"
                        )))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.entries[0].balanceDelta").value(-12_000));

        var transactions = transactionRepository.findAll();
        assertThat(transactions).hasSize(2);
        assertThat(transactions)
                .allSatisfy(transaction -> assertThat(
                        entryRepository.countByTransactionId(transaction.getId())).isEqualTo(1));
        assertThat(currentBalance(account.id())).isEqualTo(89_000);

        mockMvc.perform(get("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].type").value("EXPENSE"))
                .andExpect(jsonPath("$[1].type").value("INCOME"));

        LedgerTransaction expense = transactions.stream()
                .filter(transaction -> transaction.getType() == TransactionType.EXPENSE)
                .findFirst()
                .orElseThrow();
        mockMvc.perform(patch("/api/v1/transactions/{transactionId}", expense.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "version": 0,
                                  "type": "EXPENSE",
                                  "amount": 20000,
                                  "scope": "SHARED",
                                  "ownerMemberId": null,
                                  "payerMemberId": %d,
                                  "categoryId": %d,
                                  "accountId": %d,
                                  "occurredAt": "2026-08-27T02:00:00Z",
                                  "memo": "저녁",
                                  "adjustmentType": "NORMAL",
                                  "reversesTransactionId": null
                                }
                                """.formatted(partnerMemberId, expenseCategory.getId(), account.id())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount").value(20_000))
                .andExpect(jsonPath("$.entries[0].balanceDelta").value(-20_000))
                .andExpect(jsonPath("$.version").value(1))
                .andDo(document("ledger-transaction-update"));

        assertThat(entryRepository.countByTransactionId(expense.getId())).isEqualTo(1);
        assertThat(currentBalance(account.id())).isEqualTo(81_000);

        mockMvc.perform(patch("/api/v1/transactions/{transactionId}", expense.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "version": 0,
                                  "type": "EXPENSE",
                                  "amount": 30000,
                                  "scope": "SHARED",
                                  "ownerMemberId": null,
                                  "payerMemberId": %d,
                                  "categoryId": %d,
                                  "accountId": %d,
                                  "occurredAt": "2026-08-27T02:00:00Z",
                                  "memo": null,
                                  "adjustmentType": "NORMAL",
                                  "reversesTransactionId": null
                                }
                                """.formatted(partnerMemberId, expenseCategory.getId(), account.id())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("TRANSACTION_VERSION_CONFLICT"));

        mockMvc.perform(get("/api/v1/transactions/{transactionId}", expense.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.memo").value("저녁"))
                .andDo(document("ledger-transaction-detail"));

        mockMvc.perform(get("/api/v1/transactions")
                        .queryParam("from", "2026-08-27")
                        .queryParam("to", "2026-08-27")
                        .queryParam("type", "EXPENSE")
                        .queryParam("scope", "SHARED")
                        .queryParam("categoryId", expenseCategory.getId().toString())
                        .queryParam("accountId", account.id().toString())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(expense.getId()))
                .andDo(document("ledger-transaction-list"));

        mockMvc.perform(delete("/api/v1/transactions/{transactionId}", expense.getId())
                        .queryParam("version", "1")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf))
                .andExpect(status().isNoContent())
                .andDo(document("ledger-transaction-delete"));

        assertThat(currentBalance(account.id())).isEqualTo(101_000);
        mockMvc.perform(get("/api/v1/transactions/{transactionId}", expense.getId())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
    }

    @Test
    void should_documentCalendarMonth_when_personalScopeIsRequested() throws Exception {
        AccountResponse account = createAccount(0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "Calendar 식비");
        transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.EXPENSE,
                12_000L,
                TransactionScope.PERSONAL,
                ownerMemberId,
                ownerMemberId,
                expenseCategory.getId(),
                account.id(),
                null,
                null,
                Instant.parse("2026-08-01T03:00:00Z"),
                "8월 식비",
                AdjustmentType.NORMAL,
                null
        ));
        transactionService.create(currentHousehold, new TransactionCreateRequest(
                TransactionType.EXPENSE,
                5_000L,
                TransactionScope.PERSONAL,
                ownerMemberId,
                ownerMemberId,
                expenseCategory.getId(),
                account.id(),
                null,
                null,
                Instant.parse("2026-07-31T14:59:00Z"),
                "7월 식비",
                AdjustmentType.NORMAL,
                null
        ));

        mockMvc.perform(get("/api/v1/calendar/month")
                        .queryParam("month", "2026-08")
                        .queryParam("scope", "PERSONAL")
                        .queryParam("ownerMemberId", ownerMemberId.toString())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.month").value("2026-08"))
                .andExpect(jsonPath("$.timezone").value("Asia/Seoul"))
                .andExpect(jsonPath("$.summary.netSpendingAmount").value(12_000))
                .andExpect(jsonPath("$.summary.previousMonthNetSpendingAmount").value(5_000))
                .andExpect(jsonPath("$.summary.differenceAmount").value(7_000))
                .andExpect(jsonPath("$.days[0].date").value("2026-08-01"))
                .andExpect(jsonPath("$.days[0].transactionCount").value(1))
                .andExpect(jsonPath("$.days[0].netSpendingAmount").value(12_000))
                .andDo(document("ledger-calendar-month"));

        mockMvc.perform(get("/api/v1/calendar/month")
                        .queryParam("month", "2026-08")
                        .queryParam("scope", "PERSONAL")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.fieldErrors[0].field").value("ownerMemberId"));
    }

    @Test
    void should_documentTransferAndCardPosting_when_cardExpenseAndPaymentAreCreated()
            throws Exception {
        AccountResponse checking = createAccount(50_000);
        AccountResponse card = accountService.create(
                currentHousehold,
                new AccountCreateRequest(
                        "생활 카드",
                        null,
                        AccountType.CREDIT_CARD,
                        AccountNature.LIABILITY,
                        AccountOwnership.PERSONAL,
                        ownerMemberId,
                        0L,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        "1234",
                        false,
                        1
                )
        );
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "카드 식비");
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 12_000, "PERSONAL", ownerMemberId, ownerMemberId,
                                expenseCategory.getId(), card.id(),
                                "2026-08-27T03:00:00Z", "카드 결제"
                        )))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.entries[0].role").value("PRIMARY"))
                .andExpect(jsonPath("$.entries[0].balanceDelta").value(12_000))
                .andExpect(jsonPath("$.entries[0].account.id").value(card.id()))
                .andDo(document("ledger-card-expense-create"));

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transferJson(5_000, checking.id(), card.id())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.scope").isEmpty())
                .andExpect(jsonPath("$.category").isEmpty())
                .andExpect(jsonPath("$.entries[0].role").value("SOURCE"))
                .andExpect(jsonPath("$.entries[0].balanceDelta").value(-5_000))
                .andExpect(jsonPath("$.entries[1].role").value("DESTINATION"))
                .andExpect(jsonPath("$.entries[1].balanceDelta").value(-5_000))
                .andDo(document("ledger-transfer-create"));

        assertThat(currentBalance(checking.id())).isEqualTo(45_000);
        assertThat(currentBalance(card.id())).isEqualTo(7_000);
        mockMvc.perform(get("/api/v1/transactions")
                        .queryParam("type", "TRANSFER")
                        .queryParam("accountId", card.id().toString())
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].type").value("TRANSFER"));
    }

    @Test
    void should_hideCrossHouseholdReferenceAndRollback_when_transactionReferenceIsForeign()
            throws Exception {
        AccountResponse localAccount = createAccount(0);
        Category localCategory = createCategory(CategoryType.EXPENSE, "식비");
        User otherUser = userRepository.saveAndFlush(User.create("other-ledger@example.test", "Other"));
        Household otherHousehold = householdRepository.saveAndFlush(Household.create("Other Household"));
        HouseholdMember otherMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(otherHousehold, otherUser, HouseholdRole.OWNER));
        CurrentHousehold otherCurrent = new CurrentHousehold(
                otherUser.getId(), otherUser.getEmail(), otherUser.getDisplayName(),
                otherHousehold.getId(), otherHousehold.getName(), otherHousehold.getBaseCurrency(),
                otherHousehold.getTimezone(), HouseholdRole.OWNER
        );
        AccountResponse otherAccount = accountService.create(otherCurrent, new AccountCreateRequest(
                "Other Account", null, AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, otherMember.getId(), 0L,
                LocalDate.of(2026, 8, 1), "KRW", null, false, 0
        ));
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                localCategory.getId(), otherAccount.id(),
                                "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));

        assertThat(transactionRepository.count()).isZero();
        assertThat(entryRepository.count()).isZero();
        assertThat(currentBalance(localAccount.id())).isZero();
    }

    @Test
    void should_rejectArchivedAndUnsupportedPosting_withStableDomainErrors() throws Exception {
        AccountResponse account = createAccount(0);
        Category category = createCategory(CategoryType.EXPENSE, "식비");
        Cookie csrf = csrfCookie();

        accountService.update(currentHousehold, account.id(), new AccountUpdateRequest(
                account.name(), account.institution(), account.type(), account.nature(),
                account.ownership(), account.owner().memberId(), account.openingBalance(),
                account.openingBalanceAsOf(), account.currency(), account.lastFour(),
                account.savingsEnabled(), account.sortOrder(), true
        ));
        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                category.getId(), account.id(), "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("ARCHIVED_ACCOUNT_NOT_ALLOWED"));

        AccountResponse activeAccount = createAccount(0);
        categoryService.update(currentHousehold, category.getId(), new CategoryUpdateRequest(
                null, category.getName(), null, null, category.getSortOrder(), true));
        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                category.getId(), activeAccount.id(), "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("ARCHIVED_CATEGORY_NOT_ALLOWED"));

        Category activeCategory = createCategory(CategoryType.EXPENSE, "기타 지출");
        AccountResponse liabilityAccount = accountService.create(
                currentHousehold,
                new AccountCreateRequest(
                        "기타 부채",
                        null,
                        AccountType.OTHER,
                        AccountNature.LIABILITY,
                        AccountOwnership.PERSONAL,
                        ownerMemberId,
                        0L,
                        LocalDate.of(2026, 8, 1),
                        "KRW",
                        null,
                        false,
                        2
                )
        );
        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                activeCategory.getId(), liabilityAccount.id(),
                                "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_ACCOUNT_POSTING"));

        Long groupId = categoryGroupService.create(
                currentHousehold,
                new CategoryGroupCreateRequest("보관 Group", CategoryType.EXPENSE, 3)
        ).id();
        CategoryGroup group = categoryGroupRepository.findById(groupId).orElseThrow();
        Category groupedCategory = categoryRepository.saveAndFlush(Category.create(
                currentHousehold.householdId(),
                group.getId(),
                "Group Category",
                CategoryType.EXPENSE,
                null,
                null,
                3
        ));
        categoryGroupService.update(
                currentHousehold,
                group.getId(),
                new CategoryGroupUpdateRequest(group.getName(), group.getSortOrder(), true)
        );
        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                groupedCategory.getId(), activeAccount.id(),
                                "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("ARCHIVED_CATEGORY_NOT_ALLOWED"));
    }

    @Test
    void should_keepAuthenticationAndCsrfProtection_onLedgerEndpoints() throws Exception {
        mockMvc.perform(get("/api/v1/accounts"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));

        mockMvc.perform(get("/api/v1/transactions"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));

        mockMvc.perform(post("/api/v1/accounts")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));
    }

    @Test
    void should_rejectInvalidScopeCategoryTypeAndRefund_withStableDomainErrors()
            throws Exception {
        AccountResponse account = createAccount(0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "식비");
        Category incomeCategory = createCategory(CategoryType.INCOME, "급여");
        Cookie csrf = csrfCookie();

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", null, null,
                                expenseCategory.getId(), account.id(),
                                "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("TRANSACTION_INVALID_SCOPE"));

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(transactionJson(
                                "EXPENSE", 1000, "PERSONAL", ownerMemberId, null,
                                incomeCategory.getId(), account.id(),
                                "2026-08-27T03:00:00Z", null
                        )))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("CATEGORY_TYPE_MISMATCH"));

        mockMvc.perform(post("/api/v1/transactions")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL)
                        .header("X-XSRF-TOKEN", csrf.getValue())
                        .cookie(csrf)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "type": "EXPENSE",
                                  "amount": 1000,
                                  "scope": "PERSONAL",
                                  "ownerMemberId": %d,
                                  "payerMemberId": null,
                                  "categoryId": %d,
                                  "accountId": %d,
                                  "occurredAt": "2026-08-27T03:00:00Z",
                                  "memo": null,
                                  "adjustmentType": "REFUND",
                                  "reversesTransactionId": 999
                                }
                                """.formatted(ownerMemberId, expenseCategory.getId(), account.id())))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_ADJUSTMENT_TYPE"));

        assertThat(transactionRepository.count()).isZero();
        assertThat(entryRepository.count()).isZero();
    }

    private Cookie csrfCookie() throws Exception {
        return mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, OWNER_EMAIL))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getCookie("XSRF-TOKEN");
    }

    private AccountResponse createAccount(long openingBalance) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                "주거래 통장 " + accountRepository.count(),
                null,
                AccountType.CHECKING,
                AccountNature.ASSET,
                AccountOwnership.PERSONAL,
                ownerMemberId,
                openingBalance,
                LocalDate.of(2026, 8, 1),
                "KRW",
                null,
                false,
                (int) accountRepository.count()
        ));
    }

    private Category createCategory(CategoryType type, String name) {
        categoryService.create(currentHousehold, new CategoryCreateRequest(
                null, name, type, null, null, 0));
        return categoryRepository.findAll().stream()
                .filter(category -> category.getName().equals(name))
                .findFirst()
                .orElseThrow();
    }

    private long currentBalance(Long accountId) {
        return accountService.findAll(currentHousehold, true).stream()
                .filter(account -> account.id().equals(accountId))
                .findFirst()
                .orElseThrow()
                .currentBalance();
    }

    private String transactionJson(
            String type,
            long amount,
            String scope,
            Long owner,
            Long payer,
            Long categoryId,
            Long accountId,
            String occurredAt,
            String memo
    ) {
        return """
                {
                  "type": "%s",
                  "amount": %d,
                  "scope": "%s",
                  "ownerMemberId": %s,
                  "payerMemberId": %s,
                  "categoryId": %d,
                  "accountId": %d,
                  "sourceAccountId": null,
                  "destinationAccountId": null,
                  "occurredAt": "%s",
                  "memo": %s,
                  "adjustmentType": "NORMAL",
                  "reversesTransactionId": null
                }
                """.formatted(
                type,
                amount,
                scope,
                owner == null ? "null" : owner,
                payer == null ? "null" : payer,
                categoryId,
                accountId,
                occurredAt,
                memo == null ? "null" : "\"" + memo + "\""
        );
    }

    private String transferJson(long amount, Long sourceAccountId, Long destinationAccountId) {
        return """
                {
                  "type": "TRANSFER",
                  "amount": %d,
                  "scope": null,
                  "ownerMemberId": null,
                  "payerMemberId": null,
                  "categoryId": null,
                  "accountId": null,
                  "sourceAccountId": %d,
                  "destinationAccountId": %d,
                  "occurredAt": "2026-08-27T03:00:00Z",
                  "memo": null,
                  "adjustmentType": "NORMAL",
                  "reversesTransactionId": null
                }
                """.formatted(amount, sourceAccountId, destinationAccountId);
    }

    private void clearDatabase() {
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
