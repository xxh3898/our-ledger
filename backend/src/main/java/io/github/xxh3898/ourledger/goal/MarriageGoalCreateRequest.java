package io.github.xxh3898.ourledger.goal;

public record MarriageGoalCreateRequest(
        String name,
        Long targetAmount
) {
}
