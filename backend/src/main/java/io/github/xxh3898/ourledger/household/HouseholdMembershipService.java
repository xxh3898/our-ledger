package io.github.xxh3898.ourledger.household;

import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class HouseholdMembershipService {

    public static final int MAX_MEMBERS = 2;

    private final HouseholdRepository householdRepository;
    private final HouseholdMemberRepository householdMemberRepository;
    private final UserRepository userRepository;

    public HouseholdMembershipService(
            HouseholdRepository householdRepository,
            HouseholdMemberRepository householdMemberRepository,
            UserRepository userRepository
    ) {
        this.householdRepository = householdRepository;
        this.householdMemberRepository = householdMemberRepository;
        this.userRepository = userRepository;
    }

    @Transactional
    public HouseholdMember addMember(Long householdId, Long userId, HouseholdRole role) {
        Household household = householdRepository.findByIdForUpdate(householdId)
                .orElseThrow(() -> new IllegalArgumentException("Household를 찾을 수 없습니다."));
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new IllegalArgumentException("User를 찾을 수 없습니다."));

        if (householdMemberRepository.existsByHousehold_IdAndUser_Id(householdId, userId)) {
            throw new HouseholdMembershipConflictException("이미 Household에 참여한 User입니다.");
        }
        if (role == HouseholdRole.OWNER
                && householdMemberRepository.existsByHousehold_IdAndRole(householdId, HouseholdRole.OWNER)) {
            throw new HouseholdMembershipConflictException("Household에는 OWNER가 한 명만 존재할 수 있습니다.");
        }
        if (householdMemberRepository.countByHousehold_Id(householdId) >= MAX_MEMBERS) {
            throw new HouseholdMemberLimitExceededException();
        }

        return householdMemberRepository.saveAndFlush(HouseholdMember.create(household, user, role));
    }
}
