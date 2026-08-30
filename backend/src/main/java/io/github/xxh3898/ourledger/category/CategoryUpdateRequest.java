package io.github.xxh3898.ourledger.category;

public record CategoryUpdateRequest(
        Long groupId,
        String name,
        String iconKey,
        String colorKey,
        Integer sortOrder,
        Boolean archived
) {
}
