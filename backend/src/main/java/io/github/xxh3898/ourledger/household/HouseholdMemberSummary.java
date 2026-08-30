package io.github.xxh3898.ourledger.household;

public record HouseholdMemberSummary(
        Long memberId,
        Long userId,
        String displayName,
        HouseholdRole role
) {
}
