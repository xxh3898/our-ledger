package io.github.xxh3898.ourledger.api;

import io.github.xxh3898.ourledger.security.CurrentHousehold;

public record MeResponse(
        Long userId,
        String email,
        String displayName,
        Long householdId,
        String householdName,
        String role
) {

    public static MeResponse from(CurrentHousehold currentHousehold) {
        return new MeResponse(
                currentHousehold.userId(),
                currentHousehold.email(),
                currentHousehold.displayName(),
                currentHousehold.householdId(),
                currentHousehold.householdName(),
                currentHousehold.role().name()
        );
    }
}
