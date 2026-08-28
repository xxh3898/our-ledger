package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.assets.AssetsResponse;
import io.github.xxh3898.ourledger.assets.AssetsService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.goal.MarriageGoalCreateRequest;
import io.github.xxh3898.ourledger.goal.MarriageGoalService;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
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

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.groups.Tuple.tuple;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@ActiveProfiles("test")
@Import({TestcontainersConfiguration.class, AssetsIntegrationTest.FixedClockConfiguration.class})
@SpringBootTest
class AssetsIntegrationTest {

    private static final Instant NOW = Instant.parse("2026-08-29T00:00:00Z");

    @Autowired
    private AssetsService assetsService;

    @Autowired
    private AccountService accountService;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private MarriageGoalService marriageGoalService;

    @MockitoSpyBean
    private AccountRepository accountRepository;

    @MockitoSpyBean
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private HouseholdMemberRepository memberRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private Fixture fixture;
    private Long incomeCategoryId;
    private Long expenseCategoryId;

    @BeforeEach
    void setUp() {
        clearDatabase();
        fixture = fixture("assets", "Assets Household");
        incomeCategoryId = category("급여", CategoryType.INCOME).getId();
        expenseCategoryId = category("생활비", CategoryType.EXPENSE).getId();
    }

    @AfterEach
    void tearDown() {
        clearDatabase();
    }

    @Test
    void should_deriveCurrentSummariesAndRows_when_ledgerContainsNegativeArchivedAndGeneratedValues() {
        Long ownerAsset = account(
                "Owner 통장", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, fixture.ownerMemberId(),
                100_000, LocalDate.of(2025, 1, 1), false, 2);
        Long partnerAsset = account(
                "Partner 마이너스", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, fixture.partnerMemberId(),
                -20_000, LocalDate.of(2025, 1, 1), false, 0);
        Long sharedSavings = account(
                "공동 저축", AccountType.SAVINGS, AccountNature.ASSET,
                AccountOwnership.SHARED, null,
                0, LocalDate.of(2025, 1, 1), true, 1);
        Long zeroAsset = account(
                "공동 0원", AccountType.CASH, AccountNature.ASSET,
                AccountOwnership.SHARED, null,
                0, LocalDate.of(2025, 1, 1), false, 5);
        Long partnerCredit = account(
                "Partner 과납", AccountType.OTHER, AccountNature.LIABILITY,
                AccountOwnership.PERSONAL, fixture.partnerMemberId(),
                -10_000, LocalDate.of(2025, 1, 1), false, 1);
        Long sharedCard = account(
                "공동 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY,
                AccountOwnership.SHARED, null,
                0, LocalDate.of(2025, 1, 1), false, 0);

        income(30_000, fixture.ownerMemberId(), ownerAsset, "2026-08-01T00:00:00Z");
        TransactionResponse assetExpense = expense(
                10_000, TransactionScope.PERSONAL, fixture.ownerMemberId(),
                ownerAsset, "2026-08-02T00:00:00Z");
        transactionService.createRefund(
                fixture.currentHousehold(),
                assetExpense.id(),
                new RefundCreateRequest(
                        4_000L,
                        Instant.parse("2026-08-03T00:00:00Z"),
                        "자산 환불"
                )
        );
        TransactionResponse cardExpense = expense(
                20_000, TransactionScope.SHARED, null,
                sharedCard, "2026-08-04T00:00:00Z");
        transactionService.createRefund(
                fixture.currentHousehold(),
                cardExpense.id(),
                new RefundCreateRequest(
                        6_000L,
                        Instant.parse("2026-08-05T00:00:00Z"),
                        "카드 환불"
                )
        );
        transfer(5_000, ownerAsset, sharedCard, "2026-08-06T00:00:00Z");
        transfer(7_000, ownerAsset, sharedSavings, "2026-08-07T00:00:00Z");
        TransactionResponse generated = income(
                3_000, fixture.ownerMemberId(), ownerAsset, "2026-08-08T00:00:00Z");
        markGenerated(generated.id());
        TransactionResponse deleted = income(
                999_000, fixture.ownerMemberId(), ownerAsset, "2026-08-09T00:00:00Z");
        transactionService.delete(
                fixture.currentHousehold(), deleted.id(), deleted.version());
        archive(partnerAsset);

        AssetsResponse beforeLink = assetsService.find(fixture.currentHousehold());
        marriageGoalService.create(
                fixture.currentHousehold(),
                new MarriageGoalCreateRequest("우리 집", 100_000_000L)
        );
        marriageGoalService.linkAccount(fixture.currentHousehold(), sharedSavings);
        AssetsResponse linked = assetsService.find(fixture.currentHousehold());
        marriageGoalService.unlinkAccount(fixture.currentHousehold(), sharedSavings);
        AssetsResponse unlinked = assetsService.find(fixture.currentHousehold());

        assertThat(beforeLink.household())
                .isEqualTo(new AssetsResponse.Summary(102_000, -1_000, 103_000));
        assertThat(beforeLink.members())
                .extracting(
                        AssetsResponse.MemberSummary::displayName,
                        AssetsResponse.MemberSummary::totalAssets,
                        AssetsResponse.MemberSummary::totalLiabilities,
                        AssetsResponse.MemberSummary::netWorth
                )
                .containsExactly(
                        tuple("Owner", 115_000L, 0L, 115_000L),
                        tuple("Partner", -20_000L, -10_000L, -10_000L)
                );
        assertThat(beforeLink.shared())
                .isEqualTo(new AssetsResponse.Summary(7_000, 9_000, -2_000));
        assertThat(beforeLink.members().stream()
                .mapToLong(AssetsResponse.MemberSummary::netWorth)
                .sum() + beforeLink.shared().netWorth())
                .isEqualTo(beforeLink.household().netWorth());
        assertThat(beforeLink.accounts())
                .extracting(
                        AssetsResponse.AccountRow::name,
                        AssetsResponse.AccountRow::currentBalance,
                        AssetsResponse.AccountRow::archived
                )
                .containsExactly(
                        tuple("Owner 통장", 115_000L, false),
                        tuple("Partner 마이너스", -20_000L, true),
                        tuple("공동 저축", 7_000L, false),
                        tuple("공동 0원", 0L, false),
                        tuple("Partner 과납", -10_000L, false),
                        tuple("공동 카드", 9_000L, false)
                );
        AssetsResponse.AccountRow ownerRow = beforeLink.accounts().getFirst();
        assertThat(ownerRow.ledgerDelta()).isEqualTo(15_000);
        assertThat(linked.household()).isEqualTo(beforeLink.household());
        assertThat(unlinked.household()).isEqualTo(beforeLink.household());
        assertThat(linked.accounts()).isEqualTo(beforeLink.accounts());
        assertThat(unlinked.accounts()).isEqualTo(beforeLink.accounts());
        assertThat(zeroAsset).isNotNull();
        assertThat(partnerCredit).isNotNull();
    }

    @Test
    void should_buildElevenCompletedMonthsAndCurrentPoint_when_entriesCrossHouseholdMonthBoundary() {
        Long asset = account(
                "보관 자산", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, fixture.ownerMemberId(),
                100, LocalDate.of(2025, 1, 1), false, 0);
        Long laterAsset = account(
                "4월 시작 자산", AccountType.CASH, AccountNature.ASSET,
                AccountOwnership.SHARED, null,
                50, LocalDate.of(2026, 4, 1), false, 1);
        Long card = account(
                "월경계 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY,
                AccountOwnership.SHARED, null,
                10, LocalDate.of(2025, 1, 1), false, 0);

        income(20, fixture.ownerMemberId(), asset, "2025-09-30T14:59:59Z");
        income(30, fixture.ownerMemberId(), asset, "2025-09-30T15:00:00Z");
        TransactionResponse deleted = income(
                999, fixture.ownerMemberId(), asset, "2026-05-10T00:00:00Z");
        transactionService.delete(
                fixture.currentHousehold(), deleted.id(), deleted.version());
        expense(5, TransactionScope.SHARED, null, card, "2026-07-31T14:59:59Z");
        expense(7, TransactionScope.SHARED, null, card, "2026-07-31T15:00:00Z");
        archive(asset);

        AssetsResponse response = assetsService.find(fixture.currentHousehold());

        assertThat(response.monthlyTrend()).hasSize(12);
        assertThat(response.monthlyTrend().getFirst())
                .extracting(
                        AssetsResponse.MonthlyTrend::month,
                        AssetsResponse.MonthlyTrend::complete,
                        AssetsResponse.MonthlyTrend::assets,
                        AssetsResponse.MonthlyTrend::liabilities,
                        AssetsResponse.MonthlyTrend::netWorth
                )
                .containsExactly(YearMonth.of(2025, 9), true, 120L, 10L, 110L);
        assertTrend(response, YearMonth.of(2025, 10), 150, 10, 140);
        assertTrend(response, YearMonth.of(2026, 3), 150, 10, 140);
        assertTrend(response, YearMonth.of(2026, 4), 200, 10, 190);
        assertTrend(response, YearMonth.of(2026, 7), 200, 15, 185);
        AssetsResponse.MonthlyTrend current = response.monthlyTrend().getLast();
        assertThat(current.month()).isEqualTo(YearMonth.of(2026, 8));
        assertThat(current.complete()).isFalse();
        assertThat(current.asOf()).isEqualTo(NOW);
        assertThat(current.assets()).isEqualTo(response.household().totalAssets());
        assertThat(current.liabilities()).isEqualTo(response.household().totalLiabilities());
        assertThat(current.netWorth()).isEqualTo(response.household().netWorth());
        assertThat(response.household())
                .isEqualTo(new AssetsResponse.Summary(200, 22, 178));
        assertThat(response.accounts().stream()
                .filter(row -> row.id().equals(asset))
                .findFirst().orElseThrow().archived()).isTrue();
        assertThat(laterAsset).isNotNull();
    }

    @Test
    void should_keepTwelveZeroPointsAndActualMembers_when_householdHasNoAccounts() {
        AssetsResponse response = assetsService.find(fixture.currentHousehold());

        assertThat(response.household()).isEqualTo(new AssetsResponse.Summary(0, 0, 0));
        assertThat(response.shared()).isEqualTo(new AssetsResponse.Summary(0, 0, 0));
        assertThat(response.members()).hasSize(2)
                .allSatisfy(member -> {
                    assertThat(member.totalAssets()).isZero();
                    assertThat(member.totalLiabilities()).isZero();
                    assertThat(member.netWorth()).isZero();
                });
        assertThat(response.accounts()).isEmpty();
        assertThat(response.monthlyTrend()).hasSize(12)
                .allSatisfy(point -> {
                    assertThat(point.assets()).isZero();
                    assertThat(point.liabilities()).isZero();
                    assertThat(point.netWorth()).isZero();
                });
    }

    @Test
    void should_scopeRowsAndSummariesByAccountOwnership_when_transactionScopeDiffers() {
        Long personal = account(
                "개인 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY,
                AccountOwnership.PERSONAL, fixture.ownerMemberId(),
                0, LocalDate.of(2025, 1, 1), false, 0);
        Long shared = account(
                "공동 통장", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.SHARED, null,
                0, LocalDate.of(2025, 1, 1), false, 0);

        expense(40, TransactionScope.SHARED, null, personal, "2026-08-01T00:00:00Z");
        expense(
                15, TransactionScope.PERSONAL, fixture.ownerMemberId(),
                shared, "2026-08-02T00:00:00Z");

        AssetsResponse response = assetsService.find(fixture.currentHousehold());

        assertThat(response.members().getFirst())
                .extracting(
                        AssetsResponse.MemberSummary::totalAssets,
                        AssetsResponse.MemberSummary::totalLiabilities,
                        AssetsResponse.MemberSummary::netWorth
                )
                .containsExactly(0L, 40L, -40L);
        assertThat(response.shared()).isEqualTo(new AssetsResponse.Summary(-15, 0, -15));
        assertThat(response.household()).isEqualTo(new AssetsResponse.Summary(-15, 40, -55));
    }

    @Test
    void should_excludeForeignHouseholdData_when_readingCurrentHousehold() {
        Long local = account(
                "우리 통장", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, fixture.ownerMemberId(),
                100, LocalDate.of(2025, 1, 1), false, 0);
        income(25, fixture.ownerMemberId(), local, "2026-08-01T00:00:00Z");

        Fixture foreign = fixture("foreign-assets", "Foreign Household");
        Long foreignCategory = category(
                foreign.householdId(), "외부 급여", CategoryType.INCOME).getId();
        Long foreignAccount = account(
                foreign.currentHousehold(),
                "외부 통장", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, foreign.ownerMemberId(),
                9_000, LocalDate.of(2025, 1, 1), false, 0);
        transactionService.create(foreign.currentHousehold(), new TransactionCreateRequest(
                TransactionType.INCOME,
                1_000L,
                TransactionScope.PERSONAL,
                foreign.ownerMemberId(),
                null,
                foreignCategory,
                foreignAccount,
                null,
                null,
                Instant.parse("2026-08-01T00:00:00Z"),
                null,
                AdjustmentType.NORMAL,
                null
        ));

        AssetsResponse response = assetsService.find(fixture.currentHousehold());

        assertThat(response.household()).isEqualTo(new AssetsResponse.Summary(125, 0, 125));
        assertThat(response.accounts())
                .extracting(AssetsResponse.AccountRow::name)
                .containsExactly("우리 통장");
        assertThat(response.members())
                .extracting(AssetsResponse.MemberSummary::displayName)
                .containsExactly("Owner", "Partner");
    }

    @Test
    void should_useBoundedBatchRepositoryCalls_when_buildingAssetsReadModel() {
        account(
                "Batch 통장", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, fixture.ownerMemberId(),
                100, LocalDate.of(2025, 1, 1), false, 0);
        clearInvocations(accountRepository, entryRepository);

        assetsService.find(fixture.currentHousehold());

        verify(accountRepository, times(1))
                .sumActiveBalanceDeltas(fixture.householdId());
        verify(accountRepository, never())
                .sumActiveBalanceDelta(eq(fixture.householdId()), anyLong());
        verify(entryRepository, times(1))
                .sumActiveBalanceDeltasBefore(eq(fixture.householdId()), eq(
                        Instant.parse("2025-09-30T15:00:00Z")));
        verify(entryRepository, times(1))
                .sumActiveBalanceDeltasByLocalMonth(
                        eq(fixture.householdId()),
                        eq(Instant.parse("2025-09-30T15:00:00Z")),
                        eq(Instant.parse("2026-07-31T15:00:00Z")),
                        eq("Asia/Seoul")
                );
    }

    private void assertTrend(
            AssetsResponse response,
            YearMonth month,
            long assets,
            long liabilities,
            long netWorth
    ) {
        AssetsResponse.MonthlyTrend point = response.monthlyTrend().stream()
                .filter(item -> item.month().equals(month))
                .findFirst()
                .orElseThrow();
        assertThat(point.complete()).isTrue();
        assertThat(point.assets()).isEqualTo(assets);
        assertThat(point.liabilities()).isEqualTo(liabilities);
        assertThat(point.netWorth()).isEqualTo(netWorth);
    }

    private Long account(
            String name,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            boolean savingsEnabled,
            int sortOrder
    ) {
        return account(
                fixture.currentHousehold(),
                name,
                type,
                nature,
                ownership,
                ownerMemberId,
                openingBalance,
                openingBalanceAsOf,
                savingsEnabled,
                sortOrder
        );
    }

    private Long account(
            CurrentHousehold currentHousehold,
            String name,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            boolean savingsEnabled,
            int sortOrder
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                nature,
                ownership,
                ownerMemberId,
                openingBalance,
                openingBalanceAsOf,
                "KRW",
                null,
                savingsEnabled,
                sortOrder
        )).id();
    }

    private TransactionResponse income(
            long amount,
            Long ownerMemberId,
            Long accountId,
            String occurredAt
    ) {
        return transactionService.create(fixture.currentHousehold(), new TransactionCreateRequest(
                TransactionType.INCOME,
                amount,
                TransactionScope.PERSONAL,
                ownerMemberId,
                null,
                incomeCategoryId,
                accountId,
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
            TransactionScope scope,
            Long ownerMemberId,
            Long accountId,
            String occurredAt
    ) {
        return transactionService.create(fixture.currentHousehold(), new TransactionCreateRequest(
                TransactionType.EXPENSE,
                amount,
                scope,
                ownerMemberId,
                fixture.ownerMemberId(),
                expenseCategoryId,
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
            String occurredAt
    ) {
        return transactionService.create(fixture.currentHousehold(), new TransactionCreateRequest(
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
                null,
                AdjustmentType.NORMAL,
                null
        ));
    }

    private void archive(Long accountId) {
        Account account = accountRepository.findById(accountId).orElseThrow();
        accountService.update(fixture.currentHousehold(), accountId, new AccountUpdateRequest(
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
        ));
    }

    private void markGenerated(Long transactionId) {
        Long recurringId = jdbcTemplate.queryForObject(
                """
                INSERT INTO recurring_transactions (
                    household_id, name, type, amount, scope, owner_member_id,
                    category_id, frequency, interval_value, start_date,
                    scheduled_local_time, auto_post, active, next_recurrence_date,
                    version, created_by, updated_by
                ) VALUES (?, '생성 급여', 'INCOME', 3000, 'PERSONAL', ?, ?,
                          'MONTHLY', 1, DATE '2026-08-08', TIME '09:00',
                          TRUE, TRUE, DATE '2026-09-08', 0, ?, ?)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(),
                fixture.ownerMemberId(),
                incomeCategoryId,
                fixture.ownerMemberId(),
                fixture.ownerMemberId()
        );
        jdbcTemplate.update(
                """
                UPDATE transactions
                SET generated_from_recurring_id = ?, recurrence_date = DATE '2026-08-08'
                WHERE id = ? AND household_id = ?
                """,
                recurringId,
                transactionId,
                fixture.householdId()
        );
        transactionRepository.flush();
    }

    private Category category(String name, CategoryType type) {
        return category(fixture.householdId(), name, type);
    }

    private Category category(Long householdId, String name, CategoryType type) {
        return categoryRepository.saveAndFlush(Category.create(
                householdId,
                null,
                name,
                type,
                null,
                null,
                0
        ));
    }

    private Fixture fixture(String slug, String householdName) {
        User owner = userRepository.saveAndFlush(
                User.create(slug + "-owner@example.test", "Owner"));
        User partner = userRepository.saveAndFlush(
                User.create(slug + "-partner@example.test", "Partner"));
        Household household = householdRepository.saveAndFlush(
                Household.create(householdName));
        HouseholdMember ownerMember = memberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));
        HouseholdMember partnerMember = memberRepository.saveAndFlush(
                HouseholdMember.create(household, partner, HouseholdRole.MEMBER));
        return new Fixture(
                household.getId(),
                ownerMember.getId(),
                partnerMember.getId(),
                new CurrentHousehold(
                        owner.getId(),
                        owner.getEmail(),
                        owner.getDisplayName(),
                        household.getId(),
                        household.getName(),
                        household.getBaseCurrency(),
                        household.getTimezone(),
                        HouseholdRole.OWNER
                )
        );
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
            Long ownerMemberId,
            Long partnerMemberId,
            CurrentHousehold currentHousehold
    ) {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedClockConfiguration {

        @Bean
        @Primary
        Clock fixedAssetsClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }
}
