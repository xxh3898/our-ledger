package io.github.xxh3898.ourledger.category;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface CategoryGroupRepository extends JpaRepository<CategoryGroup, Long> {

    List<CategoryGroup> findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(Long householdId);

    List<CategoryGroup> findAllByHouseholdIdAndArchivedAtIsNullOrderByTypeAscSortOrderAscIdAsc(
            Long householdId
    );

    Optional<CategoryGroup> findByIdAndHouseholdId(Long id, Long householdId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            SELECT categoryGroup
            FROM CategoryGroup categoryGroup
            WHERE categoryGroup.id = :groupId
              AND categoryGroup.householdId = :householdId
            """)
    Optional<CategoryGroup> findByIdAndHouseholdIdForUpdate(
            @Param("groupId") Long groupId,
            @Param("householdId") Long householdId
    );
}
