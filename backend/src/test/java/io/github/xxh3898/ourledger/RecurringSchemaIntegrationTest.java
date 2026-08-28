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
class RecurringSchemaIntegrationTest {

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
    void should_applyRecurringSchema_when_v7MigrationRuns() {
        assertThat(jdbcTemplate.queryForList(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('recurring_transactions', 'recurring_transaction_accounts')
                ORDER BY table_name
                """,
                String.class
        )).containsExactly("recurring_transaction_accounts", "recurring_transactions");

        assertThat(jdbcTemplate.queryForList(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'transactions'
                  AND column_name IN ('generated_from_recurring_id', 'recurrence_date')
                ORDER BY column_name
                """,
                String.class
        )).containsExactly("generated_from_recurring_id", "recurrence_date");
    }

    @Test
    void should_enforceHouseholdChecksAndUniqueRole_when_recurringTemplateIsStored() {
        Fixture first = createFixture("recurring-first@example.test", "Recurring First");
        Fixture second = createFixture("recurring-second@example.test", "Recurring Second");
        Long firstCategory = createCategory(first, "급여", "INCOME");
        Long secondCategory = createCategory(second, "외부 급여", "INCOME");
        Long firstAccount = createAccount(first, "첫 통장");
        Long secondAccount = createAccount(second, "외부 통장");

        assertThatThrownBy(() -> insertRule(first, secondCategory))
                .isInstanceOf(DataIntegrityViolationException.class);

        Long recurringId = insertRule(first, firstCategory);
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO recurring_transaction_accounts (
                    household_id, recurring_transaction_id, account_id, entry_role
                ) VALUES (?, ?, ?, 'PRIMARY')
                """,
                first.householdId(), recurringId, secondAccount
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThat(jdbcTemplate.update(
                """
                INSERT INTO recurring_transaction_accounts (
                    household_id, recurring_transaction_id, account_id, entry_role
                ) VALUES (?, ?, ?, 'PRIMARY')
                """,
                first.householdId(), recurringId, firstAccount
        )).isEqualTo(1);
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO recurring_transaction_accounts (
                    household_id, recurring_transaction_id, account_id, entry_role
                ) VALUES (?, ?, ?, 'PRIMARY')
                """,
                first.householdId(), recurringId, firstAccount
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                "UPDATE recurring_transactions SET interval_value = 0 WHERE id = ?",
                recurringId
        )).isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbcTemplate.update(
                "UPDATE recurring_transactions SET auto_post = FALSE WHERE id = ?",
                recurringId
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_preserveOccurrenceUniqueness_when_generatedTransactionIsDeleted() {
        Fixture fixture = createFixture("lineage@example.test", "Lineage Household");
        Long categoryId = createCategory(fixture, "급여", "INCOME");
        Long recurringId = insertRule(fixture, categoryId);

        assertThatThrownBy(() -> insertGeneratedTransaction(
                fixture, categoryId, recurringId, null))
                .isInstanceOf(DataIntegrityViolationException.class);

        Long transactionId = insertGeneratedTransaction(
                fixture, categoryId, recurringId, "2026-08-28");
        jdbcTemplate.update(
                """
                UPDATE transactions
                SET deleted_at = CURRENT_TIMESTAMP, deleted_by = ?
                WHERE id = ?
                """,
                fixture.memberId(), transactionId
        );

        assertThatThrownBy(() -> insertGeneratedTransaction(
                fixture, categoryId, recurringId, "2026-08-28"))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                UPDATE transactions
                SET adjustment_type = 'REFUND', reverses_transaction_id = ?
                WHERE id = ?
                """,
                transactionId, transactionId
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    private Fixture createFixture(String email, String householdName) {
        Long userId = jdbcTemplate.queryForObject(
                "INSERT INTO users (email, display_name, status) VALUES (?, 'Fixture', 'ACTIVE') RETURNING id",
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

    private Long createCategory(Fixture fixture, String name, String type) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO categories (household_id, name, type, sort_order)
                VALUES (?, ?, ?, 0) RETURNING id
                """,
                Long.class,
                fixture.householdId(), name, type
        );
    }

    private Long createAccount(Fixture fixture, String name) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO accounts (
                    household_id, name, type, nature, ownership, owner_member_id,
                    opening_balance, opening_balance_as_of, currency,
                    savings_enabled, sort_order
                ) VALUES (?, ?, 'CHECKING', 'ASSET', 'PERSONAL', ?,
                          0, DATE '2026-08-01', 'KRW', FALSE, 0)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), name, fixture.memberId()
        );
    }

    private Long insertRule(Fixture fixture, Long categoryId) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO recurring_transactions (
                    household_id, name, type, amount, scope, owner_member_id,
                    category_id, frequency, interval_value, start_date,
                    scheduled_local_time, auto_post, active, next_recurrence_date,
                    version, created_by, updated_by
                ) VALUES (?, '월급', 'INCOME', 3000000, 'PERSONAL', ?, ?,
                          'MONTHLY', 1, DATE '2026-08-28', TIME '09:00', TRUE, TRUE,
                          DATE '2026-08-28', 0, ?, ?)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), fixture.memberId(), categoryId,
                fixture.memberId(), fixture.memberId()
        );
    }

    private Long insertGeneratedTransaction(
            Fixture fixture,
            Long categoryId,
            Long recurringId,
            String recurrenceDate
    ) {
        return jdbcTemplate.queryForObject(
                """
                INSERT INTO transactions (
                    household_id, type, amount, scope, owner_member_id, category_id,
                    occurred_at, adjustment_type, version, created_by, updated_by,
                    generated_from_recurring_id, recurrence_date
                ) VALUES (?, 'INCOME', 3000000, 'PERSONAL', ?, ?,
                          TIMESTAMPTZ '2026-08-28 09:00:00+09', 'NORMAL', 0, ?, ?, ?,
                          CAST(? AS DATE))
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), fixture.memberId(), categoryId,
                fixture.memberId(), fixture.memberId(), recurringId, recurrenceDate
        );
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

    private record Fixture(Long householdId, Long memberId) {
    }
}
