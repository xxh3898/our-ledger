package io.github.xxh3898.ourledger.bootstrap;

import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdMembershipService;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.identity.UserStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
public class HouseholdBootstrapService {

    private final UserRepository userRepository;
    private final HouseholdRepository householdRepository;
    private final HouseholdMemberRepository householdMemberRepository;
    private final HouseholdMembershipService householdMembershipService;

    public HouseholdBootstrapService(
            UserRepository userRepository,
            HouseholdRepository householdRepository,
            HouseholdMemberRepository householdMemberRepository,
            HouseholdMembershipService householdMembershipService
    ) {
        this.userRepository = userRepository;
        this.householdRepository = householdRepository;
        this.householdMemberRepository = householdMemberRepository;
        this.householdMembershipService = householdMembershipService;
    }

    @Transactional
    public HouseholdBootstrapResult provision(HouseholdBootstrapRequest request) {
        long userCount = userRepository.count();
        long householdCount = householdRepository.count();
        long membershipCount = householdMemberRepository.count();

        if (userCount == 0 && householdCount == 0 && membershipCount == 0) {
            return createInitialHousehold(request);
        }
        return verifyExactExistingState(request, userCount, householdCount, membershipCount);
    }

    private HouseholdBootstrapResult createInitialHousehold(HouseholdBootstrapRequest request) {
        User owner = userRepository.save(User.create(request.ownerEmail(), request.ownerDisplayName()));
        User member = userRepository.save(User.create(request.memberEmail(), request.memberDisplayName()));
        Household household = householdRepository.saveAndFlush(Household.create(request.householdName()));

        householdMembershipService.addMember(household.getId(), owner.getId(), HouseholdRole.OWNER);
        householdMembershipService.addMember(household.getId(), member.getId(), HouseholdRole.MEMBER);

        return new HouseholdBootstrapResult(true, household.getId(), owner.getId(), member.getId());
    }

    private HouseholdBootstrapResult verifyExactExistingState(
            HouseholdBootstrapRequest request,
            long userCount,
            long householdCount,
            long membershipCount
    ) {
        if (userCount != 2 || householdCount != 1 || membershipCount != 2) {
            throw conflict("bootstrap 대상 외 데이터 또는 부분 생성 상태가 존재합니다.");
        }

        User owner = requireUser(request.ownerEmail());
        User member = requireUser(request.memberEmail());
        Household household = householdRepository.findAll().getFirst();

        if (!owner.getDisplayName().equals(request.ownerDisplayName())
                || !member.getDisplayName().equals(request.memberDisplayName())
                || owner.getStatus() != UserStatus.ACTIVE
                || member.getStatus() != UserStatus.ACTIVE
                || !household.getName().equals(request.householdName())
                || !household.getBaseCurrency().equals(Household.DEFAULT_BASE_CURRENCY)
                || !household.getTimezone().equals(Household.DEFAULT_TIMEZONE)) {
            throw conflict("기존 User 또는 Household가 bootstrap 입력과 일치하지 않습니다.");
        }

        List<HouseholdMember> memberships = householdMemberRepository.findAll();
        boolean exactOwner = hasMembership(memberships, household, owner, HouseholdRole.OWNER);
        boolean exactMember = hasMembership(memberships, household, member, HouseholdRole.MEMBER);
        if (!exactOwner || !exactMember) {
            throw conflict("기존 Household membership이 bootstrap 입력과 일치하지 않습니다.");
        }

        return new HouseholdBootstrapResult(false, household.getId(), owner.getId(), member.getId());
    }

    private User requireUser(String email) {
        Optional<User> user = userRepository.findByEmail(email);
        return user.orElseThrow(() -> conflict("bootstrap 대상 User가 부분적으로 존재합니다."));
    }

    private boolean hasMembership(
            List<HouseholdMember> memberships,
            Household household,
            User user,
            HouseholdRole role
    ) {
        return memberships.stream().anyMatch(membership ->
                membership.getHousehold().getId().equals(household.getId())
                        && membership.getUser().getId().equals(user.getId())
                        && membership.getRole() == role
        );
    }

    private HouseholdBootstrapConflictException conflict(String message) {
        return new HouseholdBootstrapConflictException(message);
    }
}
