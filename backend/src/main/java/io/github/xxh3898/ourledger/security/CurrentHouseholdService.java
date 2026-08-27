package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.identity.EmailNormalizer;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.identity.UserStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class CurrentHouseholdService {

    private final UserRepository userRepository;
    private final HouseholdMemberRepository householdMemberRepository;

    public CurrentHouseholdService(
            UserRepository userRepository,
            HouseholdMemberRepository householdMemberRepository
    ) {
        this.userRepository = userRepository;
        this.householdMemberRepository = householdMemberRepository;
    }

    @Transactional(readOnly = true)
    public CurrentHousehold resolve(String verifiedEmail) {
        String email;
        try {
            email = EmailNormalizer.normalize(verifiedEmail);
        } catch (IllegalArgumentException exception) {
            throw new IdentityAccessDeniedException(ApiErrorCode.USER_NOT_REGISTERED);
        }

        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new IdentityAccessDeniedException(ApiErrorCode.USER_NOT_REGISTERED));
        if (user.getStatus() != UserStatus.ACTIVE) {
            throw new IdentityAccessDeniedException(ApiErrorCode.USER_DISABLED);
        }

        List<HouseholdMember> memberships = householdMemberRepository.findAllByUser_IdOrderByIdAsc(user.getId());
        if (memberships.isEmpty()) {
            throw new IdentityAccessDeniedException(ApiErrorCode.HOUSEHOLD_MEMBERSHIP_REQUIRED);
        }
        if (memberships.size() != 1) {
            throw new IdentityAccessDeniedException(ApiErrorCode.HOUSEHOLD_MEMBERSHIP_AMBIGUOUS);
        }

        HouseholdMember membership = memberships.getFirst();
        return new CurrentHousehold(
                user.getId(),
                user.getEmail(),
                user.getDisplayName(),
                membership.getHousehold().getId(),
                membership.getHousehold().getName(),
                membership.getHousehold().getBaseCurrency(),
                membership.getHousehold().getTimezone(),
                membership.getRole()
        );
    }
}
