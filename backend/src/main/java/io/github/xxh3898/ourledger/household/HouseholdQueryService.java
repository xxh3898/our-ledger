package io.github.xxh3898.ourledger.household;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class HouseholdQueryService {

    private final HouseholdMemberRepository householdMemberRepository;

    public HouseholdQueryService(HouseholdMemberRepository householdMemberRepository) {
        this.householdMemberRepository = householdMemberRepository;
    }

    @Transactional(readOnly = true)
    public List<HouseholdMemberSummary> findMembers(Long householdId) {
        return householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(householdId)
                .stream()
                .map(member -> new HouseholdMemberSummary(
                        member.getId(),
                        member.getUser().getId(),
                        member.getUser().getDisplayName(),
                        member.getRole()
                ))
                .toList();
    }
}
