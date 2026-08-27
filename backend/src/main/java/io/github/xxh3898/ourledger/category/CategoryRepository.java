package io.github.xxh3898.ourledger.category;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface CategoryRepository extends JpaRepository<Category, Long> {

    List<Category> findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(Long householdId);

    List<Category> findAllByHouseholdIdAndArchivedAtIsNullOrderByTypeAscSortOrderAscIdAsc(
            Long householdId
    );

    Optional<Category> findByIdAndHouseholdId(Long id, Long householdId);

    @Query(value = """
            SELECT EXISTS (
                SELECT 1
                FROM categories
                WHERE household_id = :householdId
                  AND type = :type
                  AND LOWER(name) = LOWER(:name)
                  AND archived_at IS NULL
                  AND (:excludedId IS NULL OR id <> :excludedId)
            )
            """, nativeQuery = true)
    boolean existsActiveName(
            @Param("householdId") Long householdId,
            @Param("type") String type,
            @Param("name") String name,
            @Param("excludedId") Long excludedId
    );
}
