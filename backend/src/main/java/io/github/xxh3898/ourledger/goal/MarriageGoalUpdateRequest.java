package io.github.xxh3898.ourledger.goal;

public record MarriageGoalUpdateRequest(
        Long version,
        String name,
        Long targetAmount
) {
}
