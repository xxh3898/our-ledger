package io.github.xxh3898.ourledger.recurring;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface RecurringTransactionRepository
        extends JpaRepository<RecurringTransaction, Long> {

    List<RecurringTransaction> findAllByHouseholdIdOrderByIdAsc(Long householdId);

    Optional<RecurringTransaction> findByIdAndHouseholdId(Long id, Long householdId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT recurring
            FROM RecurringTransaction recurring
            WHERE recurring.id = :recurringId
              AND recurring.householdId = :householdId
            """)
    Optional<RecurringTransaction> findByIdAndHouseholdIdForUpdate(
            @Param("recurringId") Long recurringId,
            @Param("householdId") Long householdId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT recurring FROM RecurringTransaction recurring WHERE recurring.id = :id")
    Optional<RecurringTransaction> findByIdForUpdate(@Param("id") Long id);

    @Query(value = """
            SELECT recurring.id
            FROM recurring_transactions recurring
            JOIN households household ON household.id = recurring.household_id
            WHERE recurring.active
              AND recurring.next_recurrence_date IS NOT NULL
              AND ((recurring.next_recurrence_date + recurring.scheduled_local_time)
                    AT TIME ZONE household.timezone) <= :now
            ORDER BY recurring.next_recurrence_date, recurring.id
            LIMIT :limit
            """, nativeQuery = true)
    List<Long> findDueIds(
            @Param("now") Instant now,
            @Param("limit") int limit
    );

    @Query(value = """
            SELECT EXISTS (
                SELECT 1
                FROM recurring_transactions recurring
                WHERE recurring.household_id = :householdId
                  AND recurring.category_id = :categoryId
                  AND recurring.active
                  AND recurring.next_recurrence_date IS NOT NULL
            )
            """, nativeQuery = true)
    boolean existsActiveForCategory(
            @Param("householdId") Long householdId,
            @Param("categoryId") Long categoryId
    );

    @Query(value = """
            SELECT EXISTS (
                SELECT 1
                FROM recurring_transactions recurring
                JOIN categories category
                  ON category.id = recurring.category_id
                 AND category.household_id = recurring.household_id
                WHERE recurring.household_id = :householdId
                  AND category.group_id = :groupId
                  AND recurring.active
                  AND recurring.next_recurrence_date IS NOT NULL
            )
            """, nativeQuery = true)
    boolean existsActiveForCategoryGroup(
            @Param("householdId") Long householdId,
            @Param("groupId") Long groupId
    );
}
