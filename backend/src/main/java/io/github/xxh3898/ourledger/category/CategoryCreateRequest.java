package io.github.xxh3898.ourledger.category;

public record CategoryCreateRequest(
        Long groupId,
        String name,
        CategoryType type,
        String iconKey,
        String colorKey,
        Integer sortOrder
) {
}
