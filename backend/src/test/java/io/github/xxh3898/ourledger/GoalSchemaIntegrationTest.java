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
class GoalSchemaIntegrationTest {

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
    void should_applyGoalTables_when_v8MigrationRuns() {
        assertThat(jdbcTemplate.queryForList(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('goals', 'goal_accounts')
                ORDER BY table_name
                """,
                String.class
        )).containsExactly("goal_accounts", "goals");
    }

    @Test
    void should_enforceMarriageTargetNameAndFutureCustomRules_when_goalsAreStored() {
        Fixture fixture = createFixture("goal-check@example.test", "Goal Check");

        Long marriageId = insertGoal(fixture, "MARRIAGE", "우리 집", 100_000_000);
        assertThat(marriageId).isPositive();
        assertThatThrownBy(() -> insertGoal(
                fixture, "MARRIAGE", "두 번째 목표", 200_000_000))
                .isInstanceOf(DataIntegrityViolationException.class);

        assertThat(insertGoal(fixture, "CUSTOM", "여행", 5_000_000)).isPositive();
        assertThat(insertGoal(fixture, "CUSTOM", "비상금", 10_000_000)).isPositive();
        assertThatThrownBy(() -> insertGoal(fixture, "CUSTOM", "   ", 10_000))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertGoal(fixture, "CUSTOM", "잘못된 목표", 0))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbcTemplate.update(
                "UPDATE goals SET version = -1 WHERE id = ?",
                marriageId
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_enforceSameHouseholdAndSingleAccountAssignment_when_linkIsStored() {
        Fixture first = createFixture("goal-first@example.test", "Goal First");
        Fixture second = createFixture("goal-second@example.test", "Goal Second");
        Long firstGoal = insertGoal(first, "MARRIAGE", "첫 목표", 100_000_000);
        Long firstCustom = insertGoal(first, "CUSTOM", "첫 커스텀", 10_000_000);
        Long secondGoal = insertGoal(second, "MARRIAGE", "외부 목표", 100_000_000);
        Long firstAccount = insertAccount(first, "첫 저축");
        Long secondAccount = insertAccount(second, "외부 저축");

        assertThat(insertLink(firstGoal, firstAccount, first, first.memberId()))
                .isEqualTo(1);
        assertThatThrownBy(() -> insertLink(
                firstCustom, firstAccount, first, first.memberId()))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertLink(
                firstGoal, secondAccount, first, first.memberId()))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> insertLink(
                secondGoal, secondAccount, second, first.memberId()))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    private Fixture createFixture(String email, String householdName) {
        Long userId = jdbcTemplate.queryForObject(
                """
                INSERT INTO users (email, display_name, status)
                VALUES (?, 'Fixture', 'ACTIVE') RETURNING id
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
                VALUES (?, ?, 'OWNER') RETURNING id
                """,
                Long.class,
                householdId, userId
        );
        return new Fixture(householdId, memberId);
    }

    private Long insertGoal(Fixture fixture, String type, String name, long targetAmount) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO goals (
                    household_id, type, name, target_amount,
                    version, created_by, updated_by
                ) VALUES (?, ?, ?, ?, 0, ?, ?) RETURNING id
                """,
                Long.class,
                fixture.householdId(), type, name, targetAmount,
                fixture.memberId(), fixture.memberId()
        );
    }

    private Long insertAccount(Fixture fixture, String name) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO accounts (
                    household_id, name, type, nature, ownership, owner_member_id,
                    opening_balance, opening_balance_as_of, currency,
                    savings_enabled, sort_order
                ) VALUES (?, ?, 'SAVINGS', 'ASSET', 'PERSONAL', ?,
                          0, DATE '2026-08-01', 'KRW', TRUE, 0)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), name, fixture.memberId()
        );
    }

    private int insertLink(
            Long goalId,
            Long accountId,
            Fixture fixture,
            Long linkedBy
    ) {
        return jdbcTemplate.update(
                """
                INSERT INTO goal_accounts (
                    goal_id, account_id, household_id,
                    starting_balance, linked_at, linked_by
                ) VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP, ?)
                """,
                goalId, accountId, fixture.householdId(), linkedBy
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

    private record Fixture(Long householdId, Long memberId) {
    }
}
