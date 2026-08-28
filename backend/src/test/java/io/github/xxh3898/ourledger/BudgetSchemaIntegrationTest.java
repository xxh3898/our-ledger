package io.github.xxh3898.ourledger;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class BudgetSchemaIntegrationTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void clearDatabaseBeforeTest() {
        clearDatabase();
    }

    @AfterEach
    void clearDatabaseAfterTest() {
        clearDatabase();
    }

    @Test
    void should_applyBudgetTable_when_v6MigrationRuns() {
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'budgets'
                """,
                Integer.class
        )).isEqualTo(1);
    }

    @Test
    void should_rejectInvalidMonthAmountAndOwner_when_budgetChecksApply() {
        Fixture fixture = createFixture("budget-check@example.test", "Budget Check");

        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-02", "HOUSEHOLD", null, null, 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-01", "HOUSEHOLD", null, null, -1))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-01", "PERSONAL", null, null, 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-01", "SHARED", fixture.memberId(), null, 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(insertBudget(
                fixture.householdId(), "2026-08-01", "PERSONAL",
                fixture.memberId(), null, 0)).isEqualTo(1);
    }

    @Test
    void should_rejectDuplicateNullIdentity_when_uniqueNullsNotDistinctApplies() {
        Fixture fixture = createFixture("budget-unique@example.test", "Budget Unique");

        assertThat(insertBudget(
                fixture.householdId(), "2026-08-01", "HOUSEHOLD", null, null, 100_000))
                .isEqualTo(1);
        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-01", "HOUSEHOLD", null, null, 200_000))
                .isInstanceOf(DataIntegrityViolationException.class);

        Long categoryId = createCategory(fixture, "식비", "EXPENSE");
        assertThat(insertBudget(
                fixture.householdId(), "2026-08-01", "PERSONAL",
                fixture.memberId(), categoryId, 50_000)).isEqualTo(1);
        assertThatThrownBy(() -> insertBudget(
                fixture.householdId(), "2026-08-01", "PERSONAL",
                fixture.memberId(), categoryId, 60_000))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_rejectCrossHouseholdMemberAndCategory_when_compositeFksApply() {
        Fixture first = createFixture("budget-first@example.test", "Budget First");
        Fixture second = createFixture("budget-second@example.test", "Budget Second");
        Long secondCategoryId = createCategory(second, "외부 식비", "EXPENSE");

        assertThatThrownBy(() -> insertBudget(
                first.householdId(), "2026-08-01", "PERSONAL",
                second.memberId(), null, 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertBudget(
                first.householdId(), "2026-08-01", "HOUSEHOLD",
                null, secondCategoryId, 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    private int insertBudget(
            Long householdId,
            String month,
            String scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        return jdbcTemplate.update(
                """
                INSERT INTO budgets (
                    household_id, budget_month, scope, owner_member_id, category_id, amount
                ) VALUES (?, ?::DATE, ?, ?, ?, ?)
                """,
                householdId, month, scope, ownerMemberId, categoryId, amount
        );
    }

    private Fixture createFixture(String email, String householdName) {
        Long userId = jdbcTemplate.queryForObject(
                """
                INSERT INTO users (email, display_name, status)
                VALUES (?, 'Fixture', 'ACTIVE')
                RETURNING id
                """,
                Long.class,
                email
        );
        Long householdId = jdbcTemplate.queryForObject(
                "INSERT INTO households (name) VALUES (?) RETURNING id",
                Long.class,
                householdName
        );
        Long memberId = jdbcTemplate.queryForObject(
                """
                INSERT INTO household_members (household_id, user_id, role)
                VALUES (?, ?, 'OWNER')
                RETURNING id
                """,
                Long.class,
                householdId, userId
        );
        return new Fixture(householdId, memberId);
    }

    private Long createCategory(Fixture fixture, String name, String type) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO categories (household_id, name, type, sort_order)
                VALUES (?, ?, ?, 0)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), name, type
        );
    }

    private void clearDatabase() {
        jdbcTemplate.execute("""
                TRUNCATE TABLE
                    budgets,
                    transaction_account_entries,
                    transactions,
                    categories,
                    category_groups,
                    accounts,
                    household_members,
                    households,
                    users
                RESTART IDENTITY CASCADE
                """);
    }

    private record Fixture(Long householdId, Long memberId) {
    }
}
