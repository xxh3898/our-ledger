package io.github.xxh3898.ourledger.category;

public record CategoryGroupUpdateRequest(
        String name,
        Integer sortOrder,
        Boolean archived
) {
}
