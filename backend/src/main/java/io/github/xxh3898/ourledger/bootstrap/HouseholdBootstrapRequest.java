package io.github.xxh3898.ourledger.bootstrap;

import io.github.xxh3898.ourledger.identity.EmailNormalizer;

public record HouseholdBootstrapRequest(
        String householdName,
        String ownerEmail,
        String ownerDisplayName,
        String memberEmail,
        String memberDisplayName
) {

    public HouseholdBootstrapRequest {
        householdName = requireText(householdName, "householdName");
        ownerEmail = EmailNormalizer.normalize(ownerEmail);
        ownerDisplayName = requireText(ownerDisplayName, "ownerDisplayName");
        memberEmail = EmailNormalizer.normalize(memberEmail);
        memberDisplayName = requireText(memberDisplayName, "memberDisplayName");
        if (ownerEmail.equals(memberEmail)) {
            throw new IllegalArgumentException("owner와 member email은 서로 달라야 합니다.");
        }
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + "은 필수입니다.");
        }
        return value.strip();
    }
}
