package io.github.xxh3898.ourledger.goal;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface GoalAccountRepository extends JpaRepository<GoalAccount, GoalAccountId> {

    List<GoalAccount> findAllByHouseholdId(Long householdId);

    List<GoalAccount> findAllByIdGoalIdAndHouseholdIdOrderByLinkedAtAsc(
            Long goalId,
            Long householdId
    );

    Optional<GoalAccount> findByIdAccountId(Long accountId);

    Optional<GoalAccount> findByIdGoalIdAndIdAccountIdAndHouseholdId(
            Long goalId,
            Long accountId,
            Long householdId
    );
}
