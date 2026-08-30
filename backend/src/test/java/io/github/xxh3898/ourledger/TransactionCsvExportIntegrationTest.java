package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.export.TransactionCsvDocument;
import io.github.xxh3898.ourledger.export.TransactionCsvExportService;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.recurring.RecurrenceFrequency;
import io.github.xxh3898.ourledger.recurring.RecurringCreateRequest;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionResponse;
import io.github.xxh3898.ourledger.recurring.RecurringTransactionService;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.RefundCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.nio.charset.StandardCharsets;
import java.sql.Date;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class TransactionCsvExportIntegrationTest {

    private static final List<String> EXPECTED_HEADER = List.of(
            "거래ID", "발생일", "발생시각", "거래유형", "조정유형", "금액",
            "귀속", "소유자", "결제자", "카테고리", "계좌", "출금계좌",
            "입금계좌", "메모", "원거래ID", "반복거래", "반복발생일",
            "생성시각", "수정시각"
    );

    @Autowired private UserRepository userRepository;
    @Autowired private HouseholdRepository householdRepository;
    @Autowired private HouseholdMemberRepository memberRepository;
    @Autowired private AccountRepository accountRepository;
    @Autowired private CategoryRepository categoryRepository;
    @Autowired private TransactionService transactionService;
    @Autowired private RecurringTransactionService recurringService;
    @Autowired private TransactionCsvExportService exportService;
    @Autowired private JdbcTemplate jdbcTemplate;
    @Autowired private EntityManager entityManager;
    @Autowired private EntityManagerFactory entityManagerFactory;

    private Fixture current;
    private Fixture foreign;
    private Account checking;
    private Account savings;
    private Account card;
    private Category expenseCategory;
    private Category incomeCategory;

    @BeforeEach
    void setUp() {
        clearDatabase();
        current = fixture(
                "current",
                "현재 Household",
                "@Owner",
                "=Partner"
        );
        foreign = fixture(
                "foreign",
                "다른 Household",
                "Foreign Owner",
                "Foreign Partner"
        );
        checking = account(current, "주거래 통장", AccountType.CHECKING,
                AccountNature.ASSET, AccountOwnership.PERSONAL,
                current.ownerMemberId(), "9876", 0);
        savings = account(current, "+비상금 통장", AccountType.SAVINGS,
                AccountNature.ASSET, AccountOwnership.SHARED,
                null, null, 1);
        card = account(current, "+생활 카드", AccountType.CREDIT_CARD,
                AccountNature.LIABILITY, AccountOwnership.SHARED,
                null, "1234", 2);
        expenseCategory = category(current, "-식비,\n\"외식\"", CategoryType.EXPENSE, 0);
        incomeCategory = category(current, "급여", CategoryType.INCOME, 1);
    }

    @AfterEach
    void tearDown() {
        entityManagerFactory.unwrap(SessionFactory.class)
                .getStatistics()
                .setStatisticsEnabled(false);
        clearDatabase();
    }

    @Test
    void should_exportCanonicalRowsSafely_when_periodContainsAllLedgerKinds() {
        Long beforeBoundary = createPrimary(
                current, TransactionType.INCOME, 1_000, TransactionScope.PERSONAL,
                current.ownerMemberId(), null, incomeCategory.getId(), checking.getId(),
                "2026-07-31T14:59:59Z", null
        ).id();
        TransactionResponse income = createPrimary(
                current, TransactionType.INCOME, 2_500_000, TransactionScope.PERSONAL,
                current.ownerMemberId(), null, incomeCategory.getId(), checking.getId(),
                "2026-07-31T15:00:00Z", null
        );
        TransactionResponse assetExpense = createPrimary(
                current, TransactionType.EXPENSE, 12_000, TransactionScope.PERSONAL,
                current.partnerMemberId(), current.ownerMemberId(), expenseCategory.getId(),
                checking.getId(), "2026-08-02T03:00:00Z", "초기 메모"
        );
        TransactionResponse cardExpense = createPrimary(
                current, TransactionType.EXPENSE, 33_000, TransactionScope.SHARED,
                null, current.partnerMemberId(), expenseCategory.getId(), card.getId(),
                "2026-08-03T03:00:00Z", null
        );
        TransactionResponse assetTransfer = createTransfer(
                current, 100_000, checking.getId(), savings.getId(),
                "2026-08-04T03:00:00Z", "저축 이동"
        );
        TransactionResponse cardPayment = createTransfer(
                current, 33_000, checking.getId(), card.getId(),
                "2026-08-04T03:00:00Z", null
        );
        TransactionResponse original = createPrimary(
                current, TransactionType.EXPENSE, 50_000, TransactionScope.PERSONAL,
                current.partnerMemberId(), current.partnerMemberId(), expenseCategory.getId(),
                checking.getId(), "2026-08-05T03:00:00Z", null
        );
        TransactionResponse partialRefund = transactionService.createRefund(
                current.currentHousehold(),
                original.id(),
                new RefundCreateRequest(20_000L, Instant.parse("2026-08-06T03:00:00Z"), null)
        );
        TransactionResponse fullRefund = transactionService.createRefund(
                current.currentHousehold(),
                original.id(),
                new RefundCreateRequest(30_000L, Instant.parse("2026-08-07T03:00:00Z"), null)
        );

        RecurringTransactionResponse recurring = recurringService.createAt(
                current.currentHousehold(),
                new RecurringCreateRequest(
                        "월급",
                        TransactionType.INCOME,
                        3_000_000L,
                        TransactionScope.PERSONAL,
                        current.ownerMemberId(),
                        null,
                        incomeCategory.getId(),
                        checking.getId(),
                        null,
                        null,
                        RecurrenceFrequency.MONTHLY,
                        1,
                        LocalDate.of(2026, 8, 20),
                        null,
                        LocalTime.of(8, 30),
                        null,
                        true,
                        true
                ),
                Instant.parse("2026-07-31T15:00:00Z")
        );
        TransactionResponse generated = createPrimary(
                current, TransactionType.INCOME, 3_000_000, TransactionScope.PERSONAL,
                current.ownerMemberId(), null, incomeCategory.getId(), checking.getId(),
                "2026-08-19T23:30:00Z", null
        );
        jdbcTemplate.update("""
                UPDATE transactions
                SET generated_from_recurring_id = ?, recurrence_date = ?
                WHERE id = ?
                """, recurring.id(), Date.valueOf("2026-08-20"), generated.id());

        TransactionResponse shared = createPrimary(
                current, TransactionType.EXPENSE, 7_000, TransactionScope.SHARED,
                null, current.ownerMemberId(), expenseCategory.getId(), checking.getId(),
                "2026-08-31T14:59:59Z", null
        );
        TransactionResponse deleted = createPrimary(
                current, TransactionType.EXPENSE, 999_999, TransactionScope.SHARED,
                null, null, expenseCategory.getId(), checking.getId(),
                "2026-08-10T03:00:00Z", "삭제된 거래"
        );
        transactionService.delete(current.currentHousehold(), deleted.id(), deleted.version());
        Long afterBoundary = createPrimary(
                current, TransactionType.INCOME, 2_000, TransactionScope.PERSONAL,
                current.ownerMemberId(), null, incomeCategory.getId(), checking.getId(),
                "2026-08-31T15:00:00Z", null
        ).id();

        Account foreignAccount = account(
                foreign, "FOREIGN-ACCOUNT", AccountType.CHECKING, AccountNature.ASSET,
                AccountOwnership.PERSONAL, foreign.ownerMemberId(), null, 0);
        Category foreignCategory = category(foreign, "FOREIGN-CATEGORY", CategoryType.EXPENSE, 0);
        Long foreignTransaction = createPrimary(
                foreign, TransactionType.EXPENSE, 88_888, TransactionScope.PERSONAL,
                foreign.ownerMemberId(), null, foreignCategory.getId(), foreignAccount.getId(),
                "2026-08-15T03:00:00Z", "FOREIGN-MEMO"
        ).id();

        archive(checking);
        archive(expenseCategory);
        jdbcTemplate.update("UPDATE accounts SET name = ? WHERE id = ?", "  =주거래 통장", checking.getId());
        jdbcTemplate.update("UPDATE transactions SET memo = ? WHERE id = ?", "\t=cmd", assetExpense.id());
        jdbcTemplate.update("UPDATE transactions SET memo = ? WHERE id = ?", "\r@cmd", shared.id());
        entityManager.clear();

        SessionFactory sessionFactory = entityManagerFactory.unwrap(SessionFactory.class);
        sessionFactory.getStatistics().setStatisticsEnabled(true);
        sessionFactory.getStatistics().clear();

        TransactionCsvDocument document = exportService.export(
                current.currentHousehold(),
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31)
        );

        assertThat(sessionFactory.getStatistics().getPrepareStatementCount()).isEqualTo(5);
        assertThat(document.filename())
                .isEqualTo("our-ledger-transactions_2026-08-01_2026-08-31.csv");
        assertThat(document.content()).startsWith((byte) 0xEF, (byte) 0xBB, (byte) 0xBF);
        String raw = new String(document.content(), StandardCharsets.UTF_8);
        assertThat(raw).startsWith("\uFEFF" + String.join(",", EXPECTED_HEADER) + "\r\n");
        assertThat(raw).endsWith("\r\n");

        List<List<String>> rows = parse(document.content());
        assertThat(rows.getFirst()).containsExactlyElementsOf(EXPECTED_HEADER);
        assertThat(rows).allSatisfy(row -> assertThat(row).hasSize(19));
        Map<Long, List<String>> byId = rowsById(rows);

        assertThat(byId).doesNotContainKeys(
                beforeBoundary,
                afterBoundary,
                deleted.id(),
                foreignTransaction
        );
        assertThat(byId.get(income.id())).containsSequence(
                income.id().toString(),
                "2026-08-01",
                "2026-08-01T00:00+09:00",
                "수입",
                "일반",
                "2500000",
                "개인",
                "'@Owner",
                "",
                "급여",
                "'  =주거래 통장"
        );
        assertThat(byId.get(assetExpense.id()).get(7)).isEqualTo("'=Partner");
        assertThat(byId.get(assetExpense.id()).get(8)).isEqualTo("'@Owner");
        assertThat(byId.get(assetExpense.id()).get(9))
                .isEqualTo("'-식비,\n\"외식\"");
        assertThat(byId.get(assetExpense.id()).get(13)).isEqualTo("'\t=cmd");
        assertThat(byId.get(cardExpense.id()).get(10)).isEqualTo("'+생활 카드");
        assertThat(byId.get(cardExpense.id()).get(8)).isEqualTo("'=Partner");
        assertThat(byId.get(assetTransfer.id()).subList(10, 13))
                .containsExactly("", "'  =주거래 통장", "'+비상금 통장");
        assertThat(byId.get(cardPayment.id()).subList(10, 13))
                .containsExactly("", "'  =주거래 통장", "'+생활 카드");
        assertThat(byId.get(partialRefund.id()).get(4)).isEqualTo("환불");
        assertThat(byId.get(partialRefund.id()).get(14)).isEqualTo(original.id().toString());
        assertThat(byId.get(fullRefund.id()).get(14)).isEqualTo(original.id().toString());
        assertThat(byId.get(generated.id()).get(15)).isEqualTo("예");
        assertThat(byId.get(generated.id()).get(16)).isEqualTo("2026-08-20");
        assertThat(byId.get(shared.id()).get(6)).isEqualTo("공동");
        assertThat(byId.get(shared.id()).get(7)).isEmpty();
        assertThat(byId.get(shared.id()).get(8)).isEqualTo("'@Owner");
        assertThat(byId.get(shared.id()).get(13)).isEqualTo("'\r@cmd");

        List<Long> sameInstantIds = rows.stream()
                .skip(1)
                .filter(row -> row.get(2).equals("2026-08-04T12:00+09:00"))
                .map(row -> Long.valueOf(row.getFirst()))
                .toList();
        assertThat(sameInstantIds).containsExactly(assetTransfer.id(), cardPayment.id());

        assertThat(raw)
                .doesNotContain("9876", "1234", current.ownerEmail(), foreign.ownerEmail())
                .doesNotContain("FOREIGN-ACCOUNT", "FOREIGN-CATEGORY", "FOREIGN-MEMO");
    }

    @Test
    void should_enforceInclusiveTenYearLimit_when_exportRangeIsValidated() {
        LocalDate from = LocalDate.of(2016, 1, 1);

        TransactionCsvDocument maximum = exportService.export(
                current.currentHousehold(), from, from.plusDays(3_652));

        assertThat(parse(maximum.content())).containsExactly(EXPECTED_HEADER);
        assertThatThrownBy(() -> exportService.export(
                current.currentHousehold(), from, from.plusDays(3_653)))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.status()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
                    assertThat(exception.code()).isEqualTo(ApiErrorCode.EXPORT_RANGE_TOO_LARGE);
                });
        assertThatThrownBy(() -> exportService.export(
                current.currentHousehold(), LocalDate.of(2026, 8, 2), LocalDate.of(2026, 8, 1)))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.status()).isEqualTo(HttpStatus.BAD_REQUEST);
                    assertThat(exception.code()).isEqualTo(ApiErrorCode.INVALID_REQUEST);
                });
        assertThatThrownBy(() -> exportService.export(
                current.currentHousehold(), null, LocalDate.of(2026, 8, 1)))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.status()).isEqualTo(HttpStatus.BAD_REQUEST);
                    assertThat(exception.code()).isEqualTo(ApiErrorCode.INVALID_REQUEST);
                });
    }

    @Test
    void should_failClosed_when_storedEntrySetIsDamaged() {
        TransactionResponse expense = createPrimary(
                current, TransactionType.EXPENSE, 12_000, TransactionScope.PERSONAL,
                current.ownerMemberId(), null, expenseCategory.getId(), checking.getId(),
                "2026-08-02T03:00:00Z", null
        );
        jdbcTemplate.update("""
                UPDATE transaction_account_entries
                SET balance_delta = -1
                WHERE transaction_id = ?
                """, expense.id());
        entityManager.clear();

        assertThatThrownBy(() -> exportService.export(
                current.currentHousehold(),
                LocalDate.of(2026, 8, 1),
                LocalDate.of(2026, 8, 31)
        )).isInstanceOfSatisfying(ApiException.class, exception -> {
            assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
            assertThat(exception.code()).isEqualTo(ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID);
        });
    }

    private TransactionResponse createPrimary(
            Fixture fixture,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            String occurredAt,
            String memo
    ) {
        return transactionService.create(
                fixture.currentHousehold(),
                new TransactionCreateRequest(
                        type,
                        amount,
                        scope,
                        ownerMemberId,
                        payerMemberId,
                        categoryId,
                        accountId,
                        null,
                        null,
                        Instant.parse(occurredAt),
                        memo,
                        AdjustmentType.NORMAL,
                        null
                )
        );
    }

    private TransactionResponse createTransfer(
            Fixture fixture,
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

    private Fixture fixture(
            String slug,
            String householdName,
            String ownerName,
            String partnerName
    ) {
        User owner = userRepository.saveAndFlush(
                User.create(slug + "-owner@example.test", ownerName));
        User partner = userRepository.saveAndFlush(
                User.create(slug + "-partner@example.test", partnerName));
        Household household = householdRepository.saveAndFlush(Household.create(householdName));
        HouseholdMember ownerMember = memberRepository.saveAndFlush(
                HouseholdMember.create(household, owner, HouseholdRole.OWNER));
        HouseholdMember partnerMember = memberRepository.saveAndFlush(
                HouseholdMember.create(household, partner, HouseholdRole.MEMBER));
        return new Fixture(
                household.getId(),
                ownerMember.getId(),
                partnerMember.getId(),
                owner.getEmail(),
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

    private Account account(
            Fixture fixture,
            String name,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            String lastFour,
            int sortOrder
    ) {
        return accountRepository.saveAndFlush(Account.create(
                fixture.householdId(),
                name,
                null,
                type,
                nature,
                ownership,
                ownerMemberId,
                0,
                LocalDate.of(2026, 1, 1),
                "KRW",
                lastFour,
                type == AccountType.SAVINGS,
                sortOrder
        ));
    }

    private Category category(
            Fixture fixture,
            String name,
            CategoryType type,
            int sortOrder
    ) {
        return categoryRepository.saveAndFlush(Category.create(
                fixture.householdId(), null, name, type, null, null, sortOrder));
    }

    private void archive(Account account) {
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

    private void archive(Category category) {
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

    private Map<Long, List<String>> rowsById(List<List<String>> rows) {
        Map<Long, List<String>> result = new LinkedHashMap<>();
        rows.stream().skip(1).forEach(row -> result.put(Long.valueOf(row.getFirst()), row));
        return result;
    }

    private List<List<String>> parse(byte[] bytes) {
        String csv = new String(bytes, StandardCharsets.UTF_8);
        assertThat(csv).startsWith("\uFEFF");
        csv = csv.substring(1);
        List<List<String>> rows = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int index = 0; index < csv.length(); index++) {
            char character = csv.charAt(index);
            if (quoted) {
                if (character == '"') {
                    if (index + 1 < csv.length() && csv.charAt(index + 1) == '"') {
                        cell.append('"');
                        index++;
                    } else {
                        quoted = false;
                    }
                } else {
                    cell.append(character);
                }
            } else if (character == '"') {
                quoted = true;
            } else if (character == ',') {
                row.add(cell.toString());
                cell.setLength(0);
            } else if (character == '\r'
                    && index + 1 < csv.length()
                    && csv.charAt(index + 1) == '\n') {
                row.add(cell.toString());
                rows.add(List.copyOf(row));
                row = new ArrayList<>();
                cell.setLength(0);
                index++;
            } else {
                cell.append(character);
            }
        }
        assertThat(quoted).isFalse();
        assertThat(row).isEmpty();
        assertThat(cell).isEmpty();
        return rows;
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
            String ownerEmail,
            CurrentHousehold currentHousehold
    ) {
    }
}
