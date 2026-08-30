package io.github.xxh3898.ourledger.category;

import java.time.Instant;

public record CategoryGroupResponse(
        Long id,
        String name,
        CategoryType type,
        int sortOrder,
        boolean archived,
        Instant createdAt,
        Instant updatedAt
) {
}
