package io.github.xxh3898.ourledger.budget;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

public interface BudgetRepository extends JpaRepository<Budget, Long> {

    Optional<Budget> findByIdAndHouseholdId(Long id, Long householdId);

    List<Budget> findAllByHouseholdIdAndBudgetMonthOrderByIdAsc(
            Long householdId,
            LocalDate budgetMonth
    );

    @Query(value = """
            SELECT EXISTS (
                SELECT 1
                FROM budgets
                WHERE household_id = :householdId
                  AND budget_month = :budgetMonth
                  AND scope = :scope
                  AND owner_member_id IS NOT DISTINCT FROM :ownerMemberId
                  AND category_id IS NOT DISTINCT FROM :categoryId
                  AND (:excludedId IS NULL OR id <> :excludedId)
            )
            """, nativeQuery = true)
    boolean existsIdentity(
            @Param("householdId") Long householdId,
            @Param("budgetMonth") LocalDate budgetMonth,
            @Param("scope") String scope,
            @Param("ownerMemberId") Long ownerMemberId,
            @Param("categoryId") Long categoryId,
            @Param("excludedId") Long excludedId
    );
}
