package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.account.AccountCreateRequest;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountOwnership;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.account.AccountResponse;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.account.AccountUpdateRequest;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryCreateRequest;
import io.github.xxh3898.ourledger.category.CategoryGroupRepository;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.category.CategoryService;
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
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionCreateRequest;
import io.github.xxh3898.ourledger.transaction.TransactionFilter;
import io.github.xxh3898.ourledger.transaction.TransactionResponse;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import io.github.xxh3898.ourledger.transaction.TransactionUpdateRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class TransferCardLedgerIntegrationTest {

    private static final String OWNER_EMAIL = "transfer-owner@example.test";
    private static final Instant OCCURRED_AT = Instant.parse("2026-08-28T03:00:00Z");

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
    private CategoryRepository categoryRepository;

    @Autowired
    private CategoryService categoryService;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private TransactionService transactionService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Transfer Household",
                OWNER_EMAIL,
                "Transfer Owner",
                "transfer-member@example.test",
                "Transfer Member"
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
    }

    @AfterEach
    void removeFixtures() {
        clearDatabase();
    }

    @Test
    void should_keepNetWorthAfterPayment_when_cardExpenseAndCardPaymentPosted() {
        AccountResponse checking = createAccount(
                "생활비 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        AccountResponse card = createAccount(
                "생활 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY, 0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "식비");

        TransactionResponse cardExpense = transactionService.create(
                currentHousehold,
                primaryRequest(
                        TransactionType.EXPENSE,
                        12_000,
                        expenseCategory.getId(),
                        card.id()
                )
        );

        assertThat(cardExpense.entries()).singleElement().satisfies(entry -> {
            assertThat(entry.role()).isEqualTo(EntryRole.PRIMARY);
            assertThat(entry.balanceDelta()).isEqualTo(12_000);
            assertThat(entry.account().id()).isEqualTo(card.id());
        });
        assertThat(currentBalance(checking.id())).isEqualTo(100_000);
        assertThat(currentBalance(card.id())).isEqualTo(12_000);
        long netWorthAfterExpense = currentBalance(checking.id()) - currentBalance(card.id());

        TransactionResponse payment = transactionService.create(
                currentHousehold,
                transferRequest(5_000, checking.id(), card.id())
        );

        assertThat(payment.scope()).isNull();
        assertThat(payment.category()).isNull();
        assertThat(payment.entries())
                .extracting(
                        TransactionResponse.Entry::role,
                        TransactionResponse.Entry::balanceDelta
                )
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple(EntryRole.SOURCE, -5_000L),
                        org.assertj.core.groups.Tuple.tuple(EntryRole.DESTINATION, -5_000L)
                );
        assertThat(currentBalance(checking.id())).isEqualTo(95_000);
        assertThat(currentBalance(card.id())).isEqualTo(7_000);
        assertThat(currentBalance(checking.id()) - currentBalance(card.id()))
                .isEqualTo(netWorthAfterExpense);
        assertThat(transactionService.findAll(
                currentHousehold,
                new TransactionFilter(null, null, TransactionType.EXPENSE, null, null, null, null)
        )).hasSize(1);
    }

    @Test
    void should_preserveAssetTotalAndRestoreBalances_when_assetTransferDeleted() {
        AccountResponse source = createAccount(
                "출금 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        AccountResponse destination = createAccount(
                "저축 통장", AccountType.SAVINGS, AccountNature.ASSET, 20_000);

        TransactionResponse transfer = transactionService.create(
                currentHousehold,
                transferRequest(30_000, source.id(), destination.id())
        );

        assertThat(currentBalance(source.id())).isEqualTo(70_000);
        assertThat(currentBalance(destination.id())).isEqualTo(50_000);
        assertThat(currentBalance(source.id()) + currentBalance(destination.id()))
                .isEqualTo(120_000);
        assertThat(transactionsForAccount(source.id())).extracting(TransactionResponse::id)
                .containsExactly(transfer.id());
        assertThat(transactionsForAccount(destination.id())).extracting(TransactionResponse::id)
                .containsExactly(transfer.id());

        transactionService.delete(currentHousehold, transfer.id(), transfer.version());

        assertThat(currentBalance(source.id())).isEqualTo(100_000);
        assertThat(currentBalance(destination.id())).isEqualTo(20_000);
        assertThat(transactionsForAccount(source.id())).isEmpty();
    }

    @Test
    void should_rebuildExactEntrySet_when_transactionTypeChanges() {
        AccountResponse source = createAccount(
                "주거래 통장", AccountType.CHECKING, AccountNature.ASSET, 100_000);
        AccountResponse destination = createAccount(
                "비상금 통장", AccountType.SAVINGS, AccountNature.ASSET, 0);
        AccountResponse card = createAccount(
                "생활 카드", AccountType.CREDIT_CARD, AccountNature.LIABILITY, 0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "생활비");
        TransactionResponse expense = transactionService.create(
                currentHousehold,
                primaryRequest(TransactionType.EXPENSE, 10_000, expenseCategory.getId(), source.id())
        );

        TransactionResponse transfer = transactionService.update(
                currentHousehold,
                expense.id(),
                transferUpdate(expense.version(), 15_000, source.id(), destination.id())
        );

        assertThat(transfer.entries()).extracting(TransactionResponse.Entry::role)
                .containsExactly(EntryRole.SOURCE, EntryRole.DESTINATION);
        assertThat(entryRepository.countByTransactionId(expense.id())).isEqualTo(2);
        assertThat(currentBalance(source.id())).isEqualTo(85_000);
        assertThat(currentBalance(destination.id())).isEqualTo(15_000);

        TransactionResponse updatedTransfer = transactionService.update(
                currentHousehold,
                expense.id(),
                transferUpdate(
                        transfer.version(),
                        6_000,
                        destination.id(),
                        source.id()
                )
        );

        assertThat(updatedTransfer.entries())
                .extracting(
                        TransactionResponse.Entry::role,
                        TransactionResponse.Entry::balanceDelta
                )
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple(EntryRole.SOURCE, -6_000L),
                        org.assertj.core.groups.Tuple.tuple(EntryRole.DESTINATION, 6_000L)
                );
        assertThat(updatedTransfer.entries().getFirst().account().id())
                .isEqualTo(destination.id());
        assertThat(updatedTransfer.entries().getLast().account().id())
                .isEqualTo(source.id());
        assertThat(currentBalance(source.id())).isEqualTo(106_000);
        assertThat(currentBalance(destination.id())).isEqualTo(-6_000);

        TransactionResponse cardExpense = transactionService.update(
                currentHousehold,
                expense.id(),
                primaryUpdate(
                        updatedTransfer.version(),
                        TransactionType.EXPENSE,
                        20_000,
                        expenseCategory.getId(),
                        card.id()
                )
        );

        assertThat(cardExpense.entries()).singleElement()
                .extracting(TransactionResponse.Entry::role)
                .isEqualTo(EntryRole.PRIMARY);
        assertThat(entryRepository.countByTransactionId(expense.id())).isEqualTo(1);
        assertThat(currentBalance(source.id())).isEqualTo(100_000);
        assertThat(currentBalance(destination.id())).isZero();
        assertThat(currentBalance(card.id())).isEqualTo(20_000);

        transactionService.delete(currentHousehold, cardExpense.id(), cardExpense.version());

        assertThat(currentBalance(card.id())).isZero();
        assertThat(transactionsForAccount(card.id())).isEmpty();
    }

    @Test
    void should_rollbackAllRows_when_transferReferencesAreInvalid() {
        AccountResponse asset = createAccount(
                "정상 통장", AccountType.CHECKING, AccountNature.ASSET, 0);
        AccountResponse liability = createAccount(
                "기타 부채", AccountType.OTHER, AccountNature.LIABILITY, 0);
        AccountResponse archived = createAccount(
                "보관 통장", AccountType.SAVINGS, AccountNature.ASSET, 0);
        archive(archived);
        AccountResponse foreign = createForeignAccount();

        assertApiError(
                ApiErrorCode.TRANSFER_SAME_ACCOUNT_NOT_ALLOWED,
                () -> transactionService.create(
                        currentHousehold,
                        transferRequest(1_000, asset.id(), asset.id()))
        );
        assertApiError(
                ApiErrorCode.UNSUPPORTED_TRANSFER_SOURCE,
                () -> transactionService.create(
                        currentHousehold,
                        transferRequest(1_000, liability.id(), asset.id()))
        );
        assertApiError(
                ApiErrorCode.ARCHIVED_ACCOUNT_NOT_ALLOWED,
                () -> transactionService.create(
                        currentHousehold,
                        transferRequest(1_000, asset.id(), archived.id()))
        );
        assertApiError(
                ApiErrorCode.RESOURCE_NOT_FOUND,
                () -> transactionService.create(
                        currentHousehold,
                        transferRequest(1_000, asset.id(), foreign.id()))
        );

        assertThat(transactionRepository.count()).isZero();
        assertThat(entryRepository.count()).isZero();
    }

    @Test
    void should_rejectUnsupportedAccountShapes_when_accountOrExpenseIsInvalid() {
        assertApiError(
                ApiErrorCode.CREDIT_CARD_NATURE_REQUIRED,
                () -> createAccount(
                        "잘못된 카드", AccountType.CREDIT_CARD, AccountNature.ASSET, 0)
        );

        AccountResponse liability = createAccount(
                "기타 부채", AccountType.OTHER, AccountNature.LIABILITY, 0);
        Category expenseCategory = createCategory(CategoryType.EXPENSE, "기타 지출");
        Category incomeCategory = createCategory(CategoryType.INCOME, "기타 수입");
        assertApiError(
                ApiErrorCode.UNSUPPORTED_ACCOUNT_POSTING,
                () -> transactionService.create(
                        currentHousehold,
                        primaryRequest(
                                TransactionType.EXPENSE,
                                1_000,
                                expenseCategory.getId(),
                                liability.id()
                        ))
        );
        assertApiError(
                ApiErrorCode.UNSUPPORTED_ACCOUNT_POSTING,
                () -> transactionService.create(
                        currentHousehold,
                        primaryRequest(
                                TransactionType.INCOME,
                                1_000,
                                incomeCategory.getId(),
                                liability.id()
                        ))
        );

        assertThat(transactionRepository.count()).isZero();
        assertThat(entryRepository.count()).isZero();
    }

    @Test
    void should_returnStableConflict_when_storedEntrySetIsIncomplete() {
        AccountResponse source = createAccount(
                "출금 통장", AccountType.CHECKING, AccountNature.ASSET, 0);
        AccountResponse destination = createAccount(
                "입금 통장", AccountType.SAVINGS, AccountNature.ASSET, 0);
        TransactionResponse transfer = transactionService.create(
                currentHousehold,
                transferRequest(1_000, source.id(), destination.id())
        );
        jdbcTemplate.update(
                """
                DELETE FROM transaction_account_entries
                WHERE transaction_id = ? AND entry_role = 'DESTINATION'
                """,
                transfer.id()
        );

        assertApiError(
                ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID,
                () -> transactionService.findOne(currentHousehold, transfer.id())
        );
    }

    private TransactionCreateRequest primaryRequest(
            TransactionType type,
            long amount,
            Long categoryId,
            Long accountId
    ) {
        return new TransactionCreateRequest(
                type,
                amount,
                TransactionScope.PERSONAL,
                ownerMemberId,
                type == TransactionType.EXPENSE ? ownerMemberId : null,
                categoryId,
                accountId,
                null,
                null,
                OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private TransactionCreateRequest transferRequest(
            long amount,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        return new TransactionCreateRequest(
                TransactionType.TRANSFER,
                amount,
                null,
                null,
                null,
                null,
                null,
                sourceAccountId,
                destinationAccountId,
                OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private TransactionUpdateRequest transferUpdate(
            long version,
            long amount,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        return new TransactionUpdateRequest(
                version,
                TransactionType.TRANSFER,
                amount,
                null,
                null,
                null,
                null,
                null,
                sourceAccountId,
                destinationAccountId,
                OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private TransactionUpdateRequest primaryUpdate(
            long version,
            TransactionType type,
            long amount,
            Long categoryId,
            Long accountId
    ) {
        return new TransactionUpdateRequest(
                version,
                type,
                amount,
                TransactionScope.PERSONAL,
                ownerMemberId,
                type == TransactionType.EXPENSE ? ownerMemberId : null,
                categoryId,
                accountId,
                null,
                null,
                OCCURRED_AT,
                null,
                AdjustmentType.NORMAL,
                null
        );
    }

    private AccountResponse createAccount(
            String name,
            AccountType type,
            AccountNature nature,
            long openingBalance
    ) {
        return accountService.create(currentHousehold, new AccountCreateRequest(
                name,
                null,
                type,
                nature,
                AccountOwnership.PERSONAL,
                ownerMemberId,
                openingBalance,
                LocalDate.of(2026, 8, 1),
                "KRW",
                null,
                type == AccountType.SAVINGS,
                (int) accountRepository.count()
        ));
    }

    private void archive(AccountResponse account) {
        accountService.update(currentHousehold, account.id(), new AccountUpdateRequest(
                account.name(),
                account.institution(),
                account.type(),
                account.nature(),
                account.ownership(),
                account.owner().memberId(),
                account.openingBalance(),
                account.openingBalanceAsOf(),
                account.currency(),
                account.lastFour(),
                account.savingsEnabled(),
                account.sortOrder(),
                true
        ));
    }

    private AccountResponse createForeignAccount() {
        User user = userRepository.saveAndFlush(User.create(
                "foreign-transfer@example.test", "Foreign"));
        Household household = householdRepository.saveAndFlush(
                Household.create("Foreign Household"));
        HouseholdMember member = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(household, user, HouseholdRole.OWNER));
        CurrentHousehold foreignCurrent = new CurrentHousehold(
                user.getId(),
                user.getEmail(),
                user.getDisplayName(),
                household.getId(),
                household.getName(),
                household.getBaseCurrency(),
                household.getTimezone(),
                HouseholdRole.OWNER
        );
        return accountService.create(foreignCurrent, new AccountCreateRequest(
                "Foreign Account",
                null,
                AccountType.CHECKING,
                AccountNature.ASSET,
                AccountOwnership.PERSONAL,
                member.getId(),
                0L,
                LocalDate.of(2026, 8, 1),
                "KRW",
                null,
                false,
                0
        ));
    }

    private Category createCategory(CategoryType type, String name) {
        categoryService.create(currentHousehold, new CategoryCreateRequest(
                null,
                name,
                type,
                null,
                null,
                0
        ));
        return categoryRepository.findAll().stream()
                .filter(category -> category.getName().equals(name))
                .findFirst()
                .orElseThrow();
    }

    private List<TransactionResponse> transactionsForAccount(Long accountId) {
        return transactionService.findAll(
                currentHousehold,
                new TransactionFilter(null, null, null, null, null, null, accountId)
        );
    }

    private long currentBalance(Long accountId) {
        return accountService.findAll(currentHousehold, true).stream()
                .filter(account -> account.id().equals(accountId))
                .findFirst()
                .orElseThrow()
                .currentBalance();
    }

    private void assertApiError(ApiErrorCode code, Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(
                        ApiException.class,
                        exception -> assertThat(exception.code()).isEqualTo(code)
                );
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
