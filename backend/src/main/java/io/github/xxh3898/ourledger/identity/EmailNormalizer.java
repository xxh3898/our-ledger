package io.github.xxh3898.ourledger.identity;

import java.util.Locale;

public final class EmailNormalizer {

    private static final int MAX_EMAIL_LENGTH = 320;

    private EmailNormalizer() {
    }

    public static String normalize(String email) {
        if (email == null) {
            throw new IllegalArgumentException("email은 필수입니다.");
        }

        String normalized = email.strip().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty() || normalized.length() > MAX_EMAIL_LENGTH) {
            throw new IllegalArgumentException("email 형식이 유효하지 않습니다.");
        }
        return normalized;
    }
}
