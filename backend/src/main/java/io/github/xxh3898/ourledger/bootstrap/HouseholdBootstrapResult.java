package io.github.xxh3898.ourledger.bootstrap;

public record HouseholdBootstrapResult(
        boolean created,
        Long householdId,
        Long ownerUserId,
        Long memberUserId
) {
}
