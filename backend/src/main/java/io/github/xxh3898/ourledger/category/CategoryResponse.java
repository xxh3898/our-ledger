package io.github.xxh3898.ourledger.category;

import java.time.Instant;

public record CategoryResponse(
        Long id,
        Group group,
        String name,
        CategoryType type,
        String iconKey,
        String colorKey,
        int sortOrder,
        boolean archived,
        Instant createdAt,
        Instant updatedAt
) {

    public record Group(Long id, String name, CategoryType type, boolean archived) {
    }
}
