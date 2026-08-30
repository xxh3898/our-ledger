package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.calendar.CalendarMonthResponse;
import io.github.xxh3898.ourledger.calendar.CalendarService;
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
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
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

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.groups.Tuple.tuple;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class CalendarMonthIntegrationTest {

    private static final String OWNER_EMAIL = "calendar-owner@example.test";

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdBootstrapService householdBootstrapService;

    @Autowired
    private CategoryRepository categoryRepository;

    @Autowired
    private CategoryGroupRepository categoryGroupRepository;

    @Autowired
    private LedgerTransactionRepository transactionRepository;

    @Autowired
    private TransactionAccountEntryRepository entryRepository;

    @Autowired
    private CalendarService calendarService;

    private CurrentHousehold currentHousehold;
    private Long ownerMemberId;
    private Long partnerMemberId;
    private Long expenseCategoryId;
    private Long incomeCategoryId;

    @BeforeEach
    void provisionHousehold() {
        clearDatabase();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "Calendar Household",
                OWNER_EMAIL,
                "Calendar Owner",
                "calendar-member@example.test",
                "Calendar Member"
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
        expenseCategoryId = categoryRepository.saveAndFlush(Category.create(
                household.getId(), null, "식비", CategoryType.EXPENSE,
                null, null, 0
        )).getId();
        incomeCategoryId = categoryRepository.saveAndFlush(Category.create(
                household.getId(), null, "급여", CategoryType.INCOME,
                null, null, 1
        )).getId();
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
    void should_aggregateNetSpendingAndDays_when_monthContainsAllTransactionKinds() {
        LedgerTransaction original = saveTransaction(
                TransactionType.EXPENSE,
                30_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                expenseCategoryId,
                "2026-07-31T15:05:00Z",
                AdjustmentType.NORMAL,
                null
        );
        saveTransaction(
                TransactionType.EXPENSE,
                8_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                expenseCategoryId,
                "2026-08-02T03:00:00Z",
                AdjustmentType.REFUND,
                original.getId()
        );
        saveTransaction(
                TransactionType.EXPENSE,
                20_000,
                TransactionScope.PERSONAL,
                partnerMemberId,
                expenseCategoryId,
                "2026-08-01T03:00:00Z",
                AdjustmentType.NORMAL,
                null
        );
        saveTransaction(
                TransactionType.EXPENSE,
                15_000,
                TransactionScope.SHARED,
                null,
                expenseCategoryId,
                "2026-08-01T04:00:00Z",
                AdjustmentType.NORMAL,
                null
        );
        saveTransaction(
                TransactionType.INCOME,
                70_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                incomeCategoryId,
                "2026-08-03T02:00:00Z",
                AdjustmentType.NORMAL,
                null
        );
        saveTransaction(
                TransactionType.TRANSFER,
                5_000,
                null,
                null,
                null,
                "2026-08-03T03:00:00Z",
                AdjustmentType.NORMAL,
                null
        );
        LedgerTransaction deleted = saveTransaction(
                TransactionType.EXPENSE,
                99_000,
                TransactionScope.PERSONAL,
                ownerMemberId,
                expenseCategoryId,
                "2026-08-04T03:00:00Z",
                AdjustmentType.NORMAL,
                null
        );
        deleted.delete(ownerMemberId);
        transactionRepository.saveAndFlush(deleted);

        savePreviousExpense(10_000, TransactionScope.PERSONAL, ownerMemberId, "2026-07-10T03:00:00Z");
        savePreviousExpense(5_000, TransactionScope.PERSONAL, partnerMemberId, "2026-07-20T03:00:00Z");
        savePreviousExpense(3_000, TransactionScope.SHARED, null, "2026-07-31T14:59:00Z");

        CalendarMonthResponse response = calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                null,
                null
        );

        assertThat(response.month()).isEqualTo(YearMonth.of(2026, 8));
        assertThat(response.timezone()).isEqualTo("Asia/Seoul");
        assertThat(response.summary())
                .extracting(
                        CalendarMonthResponse.Summary::netSpendingAmount,
                        CalendarMonthResponse.Summary::previousMonthNetSpendingAmount,
                        CalendarMonthResponse.Summary::differenceAmount
                )
                .containsExactly(57_000L, 18_000L, 39_000L);
        assertThat(response.days())
                .extracting(
                        CalendarMonthResponse.Day::date,
                        CalendarMonthResponse.Day::transactionCount,
                        CalendarMonthResponse.Day::netSpendingAmount
                )
                .containsExactly(
                        tuple(LocalDate.of(2026, 8, 1), 3L, 65_000L),
                        tuple(LocalDate.of(2026, 8, 2), 1L, -8_000L),
                        tuple(LocalDate.of(2026, 8, 3), 2L, 0L)
                );
        assertThat(response.days().stream()
                .mapToLong(CalendarMonthResponse.Day::netSpendingAmount)
                .sum()).isEqualTo(response.summary().netSpendingAmount());
    }

    @Test
    void should_splitSameTransactions_when_scopeChanges() {
        seedScopeTransactions();

        CalendarMonthResponse owner = calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                TransactionScope.PERSONAL,
                ownerMemberId
        );
        CalendarMonthResponse partner = calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                TransactionScope.PERSONAL,
                partnerMemberId
        );
        CalendarMonthResponse shared = calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                TransactionScope.SHARED,
                null
        );

        assertThat(owner.summary().netSpendingAmount()).isEqualTo(12_000);
        assertThat(partner.summary().netSpendingAmount()).isEqualTo(7_000);
        assertThat(shared.summary().netSpendingAmount()).isEqualTo(5_000);
        assertThat(owner.days()).singleElement()
                .extracting(CalendarMonthResponse.Day::transactionCount)
                .isEqualTo(1L);
        assertThat(partner.days()).singleElement()
                .extracting(CalendarMonthResponse.Day::transactionCount)
                .isEqualTo(1L);
        assertThat(shared.days()).singleElement()
                .extracting(CalendarMonthResponse.Day::transactionCount)
                .isEqualTo(1L);
    }

    @Test
    void should_rejectInvalidOwnerCombination_when_calendarFilterIsInvalid() {
        assertBadRequest(() -> calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), TransactionScope.PERSONAL, null));
        assertBadRequest(() -> calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), null, ownerMemberId));
        assertBadRequest(() -> calendarService.findMonth(
                currentHousehold, YearMonth.of(2026, 8), TransactionScope.SHARED, ownerMemberId));
    }

    @Test
    void should_hideForeignMember_when_personalScopeUsesOtherHouseholdMember() {
        User foreignUser = userRepository.saveAndFlush(
                User.create("foreign-calendar@example.test", "Foreign Member"));
        Household foreignHousehold = householdRepository.saveAndFlush(
                Household.create("Foreign Household"));
        HouseholdMember foreignMember = householdMemberRepository.saveAndFlush(
                HouseholdMember.create(foreignHousehold, foreignUser, HouseholdRole.OWNER));

        assertThatThrownBy(() -> calendarService.findMonth(
                currentHousehold,
                YearMonth.of(2026, 8),
                TransactionScope.PERSONAL,
                foreignMember.getId()
        )).isInstanceOfSatisfying(ApiException.class, exception ->
                assertThat(exception.status()).isEqualTo(HttpStatus.NOT_FOUND));
    }

    private void seedScopeTransactions() {
        savePreviousExpense(12_000, TransactionScope.PERSONAL, ownerMemberId, "2026-08-05T03:00:00Z");
        savePreviousExpense(7_000, TransactionScope.PERSONAL, partnerMemberId, "2026-08-05T04:00:00Z");
        savePreviousExpense(5_000, TransactionScope.SHARED, null, "2026-08-05T05:00:00Z");
        saveTransaction(
                TransactionType.TRANSFER, 3_000, null, null, null,
                "2026-08-05T06:00:00Z", AdjustmentType.NORMAL, null
        );
    }

    private void savePreviousExpense(
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            String occurredAt
    ) {
        saveTransaction(
                TransactionType.EXPENSE,
                amount,
                scope,
                ownerMemberId,
                expenseCategoryId,
                occurredAt,
                AdjustmentType.NORMAL,
                null
        );
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

    private void assertBadRequest(Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.status()).isEqualTo(HttpStatus.BAD_REQUEST));
    }

    private void clearDatabase() {
        entryRepository.deleteAllInBatch();
        transactionRepository.deleteAllInBatch();
        categoryRepository.deleteAllInBatch();
        categoryGroupRepository.deleteAllInBatch();
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
    }
}
