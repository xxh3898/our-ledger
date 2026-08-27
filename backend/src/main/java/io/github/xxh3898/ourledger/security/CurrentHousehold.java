package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.household.HouseholdRole;

public record CurrentHousehold(
        Long userId,
        String email,
        String displayName,
        Long householdId,
        String householdName,
        String baseCurrency,
        String timezone,
        HouseholdRole role
) {
}
