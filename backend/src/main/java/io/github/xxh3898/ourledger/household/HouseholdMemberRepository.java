package io.github.xxh3898.ourledger.household;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface HouseholdMemberRepository extends JpaRepository<HouseholdMember, Long> {

    boolean existsByHousehold_IdAndUser_Id(Long householdId, Long userId);

    boolean existsByHousehold_IdAndRole(Long householdId, HouseholdRole role);

    long countByHousehold_Id(Long householdId);

    @EntityGraph(attributePaths = {"household", "user"})
    List<HouseholdMember> findAllByUser_IdOrderByIdAsc(Long userId);

    @EntityGraph(attributePaths = {"user"})
    List<HouseholdMember> findAllByHousehold_IdOrderByJoinedAtAscIdAsc(Long householdId);

    @EntityGraph(attributePaths = {"user"})
    Optional<HouseholdMember> findByIdAndHousehold_Id(Long id, Long householdId);

    @EntityGraph(attributePaths = {"user"})
    Optional<HouseholdMember> findByHousehold_IdAndUser_Id(Long householdId, Long userId);
}
