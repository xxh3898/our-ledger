package io.github.xxh3898.ourledger;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class LedgerSchemaIntegrationTest {

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
    void should_applyLedgerTables_when_v3AndV4MigrationsRun() {
        assertThat(jdbcTemplate.queryForList(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'accounts',
                    'categories',
                    'category_groups',
                    'transaction_account_entries',
                    'transactions'
                  )
                ORDER BY table_name
                """,
                String.class
        )).containsExactly(
                "accounts",
                "categories",
                "category_groups",
                "transaction_account_entries",
                "transactions"
        );
    }

    @Test
    void should_rejectInvalidAccountOwnershipAndCrossHouseholdOwner_when_constraintsApply() {
        Fixture first = createFixture("first@example.test", "First Household");
        Fixture second = createFixture("second@example.test", "Second Household");

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO accounts (
                    household_id, name, type, nature, ownership, owner_member_id,
                    opening_balance, opening_balance_as_of, currency,
                    savings_enabled, sort_order
                ) VALUES (?, 'Invalid personal', 'CHECKING', 'ASSET', 'PERSONAL', NULL,
                          0, DATE '2026-08-01', 'KRW', FALSE, 0)
                """,
                first.householdId()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO accounts (
                    household_id, name, type, nature, ownership, owner_member_id,
                    opening_balance, opening_balance_as_of, currency,
                    savings_enabled, sort_order
                ) VALUES (?, 'Cross tenant', 'CHECKING', 'ASSET', 'PERSONAL', ?,
                          0, DATE '2026-08-01', 'KRW', FALSE, 0)
                """,
                first.householdId(), second.memberId()
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void should_enforceCategoryGroupTypeAndActiveCaseInsensitiveName_when_constraintsApply() {
        Fixture fixture = createFixture("category@example.test", "Category Household");
        Long groupId = jdbcTemplate.queryForObject(
                """
                INSERT INTO category_groups (household_id, name, type, sort_order)
                VALUES (?, 'Expense group', 'EXPENSE', 0)
                RETURNING id
                """,
                Long.class,
                fixture.householdId()
        );

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO categories (household_id, group_id, name, type, sort_order)
                VALUES (?, ?, 'Salary', 'INCOME', 0)
                """,
                fixture.householdId(), groupId
        )).isInstanceOf(DataIntegrityViolationException.class);

        Long categoryId = jdbcTemplate.queryForObject(
                """
                INSERT INTO categories (household_id, group_id, name, type, sort_order)
                VALUES (?, ?, 'Food', 'EXPENSE', 0)
                RETURNING id
                """,
                Long.class,
                fixture.householdId(), groupId
        );
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO categories (household_id, group_id, name, type, sort_order)
                VALUES (?, ?, 'FOOD', 'EXPENSE', 1)
                """,
                fixture.householdId(), groupId
        )).isInstanceOf(DataIntegrityViolationException.class);

        jdbcTemplate.update(
                "UPDATE categories SET archived_at = CURRENT_TIMESTAMP WHERE id = ?",
                categoryId
        );
        assertThat(jdbcTemplate.update(
                """
                INSERT INTO categories (household_id, group_id, name, type, sort_order)
                VALUES (?, ?, 'FOOD', 'EXPENSE', 1)
                """,
                fixture.householdId(), groupId
        )).isEqualTo(1);
    }

    @Test
    void should_rejectInvalidTransactionAndCrossHouseholdEntry_when_constraintsApply() {
        Fixture first = createFixture("ledger-first@example.test", "Ledger First");
        Fixture second = createFixture("ledger-second@example.test", "Ledger Second");
        Long firstAccount = createAccount(first, "First account");
        Long secondAccount = createAccount(second, "Second account");
        Long categoryId = createCategory(first, "Expense", "EXPENSE");

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO transactions (
                    household_id, type, amount, scope, owner_member_id, category_id,
                    occurred_at, adjustment_type, version, created_by, updated_by
                ) VALUES (?, 'EXPENSE', 0, 'PERSONAL', ?, ?, CURRENT_TIMESTAMP,
                          'NORMAL', 0, ?, ?)
                """,
                first.householdId(), first.memberId(), categoryId,
                first.memberId(), first.memberId()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO transactions (
                    household_id, type, amount, scope, owner_member_id, category_id,
                    occurred_at, adjustment_type, version, created_by, updated_by
                ) VALUES (?, 'EXPENSE', 1000, 'PERSONAL', ?, ?, CURRENT_TIMESTAMP,
                          'NORMAL', 0, ?, ?)
                """,
                first.householdId(), second.memberId(), categoryId,
                first.memberId(), first.memberId()
        )).isInstanceOf(DataIntegrityViolationException.class);

        Long transactionId = jdbcTemplate.queryForObject(
                """
                INSERT INTO transactions (
                    household_id, type, amount, scope, owner_member_id, category_id,
                    occurred_at, adjustment_type, version, created_by, updated_by
                ) VALUES (?, 'EXPENSE', 1000, 'PERSONAL', ?, ?, CURRENT_TIMESTAMP,
                          'NORMAL', 0, ?, ?)
                RETURNING id
                """,
                Long.class,
                first.householdId(), first.memberId(), categoryId,
                first.memberId(), first.memberId()
        );

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO transaction_account_entries (
                    household_id, transaction_id, account_id, entry_role, balance_delta
                ) VALUES (?, ?, ?, 'PRIMARY', -1000)
                """,
                first.householdId(), transactionId, secondAccount
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThat(jdbcTemplate.update(
                """
                INSERT INTO transaction_account_entries (
                    household_id, transaction_id, account_id, entry_role, balance_delta
                ) VALUES (?, ?, ?, 'PRIMARY', -1000)
                """,
                first.householdId(), transactionId, firstAccount
        )).isEqualTo(1);
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO transaction_account_entries (
                    household_id, transaction_id, account_id, entry_role, balance_delta
                ) VALUES (?, ?, ?, 'PRIMARY', -1000)
                """,
                first.householdId(), transactionId, firstAccount
        )).isInstanceOf(DataIntegrityViolationException.class);
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
                """
                INSERT INTO households (name) VALUES (?) RETURNING id
                """,
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
