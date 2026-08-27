package io.github.xxh3898.ourledger.category;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface CategoryGroupRepository extends JpaRepository<CategoryGroup, Long> {

    List<CategoryGroup> findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(Long householdId);

    List<CategoryGroup> findAllByHouseholdIdAndArchivedAtIsNullOrderByTypeAscSortOrderAscIdAsc(
            Long householdId
    );

    Optional<CategoryGroup> findByIdAndHouseholdId(Long id, Long householdId);
}
