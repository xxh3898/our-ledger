package io.github.xxh3898.ourledger.category;

public record CategoryGroupCreateRequest(
        String name,
        CategoryType type,
        Integer sortOrder
) {
}
