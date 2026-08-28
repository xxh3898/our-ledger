package io.github.xxh3898.ourledger.goal;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface GoalRepository extends JpaRepository<Goal, Long> {

    Optional<Goal> findByHouseholdIdAndType(Long householdId, GoalType type);

    boolean existsByHouseholdIdAndType(Long householdId, GoalType type);
}
