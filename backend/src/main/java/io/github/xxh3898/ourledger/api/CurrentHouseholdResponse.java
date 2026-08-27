package io.github.xxh3898.ourledger.api;

import io.github.xxh3898.ourledger.household.HouseholdMemberSummary;
import io.github.xxh3898.ourledger.security.CurrentHousehold;

import java.util.List;

public record CurrentHouseholdResponse(
        Long householdId,
        String name,
        String baseCurrency,
        String timezone,
        List<Member> members
) {

    public static CurrentHouseholdResponse from(
            CurrentHousehold currentHousehold,
            List<HouseholdMemberSummary> members
    ) {
        return new CurrentHouseholdResponse(
                currentHousehold.householdId(),
                currentHousehold.householdName(),
                currentHousehold.baseCurrency(),
                currentHousehold.timezone(),
                members.stream().map(Member::from).toList()
        );
    }

    public record Member(Long userId, String displayName, String role) {

        static Member from(HouseholdMemberSummary member) {
            return new Member(member.userId(), member.displayName(), member.role().name());
        }
    }
}
