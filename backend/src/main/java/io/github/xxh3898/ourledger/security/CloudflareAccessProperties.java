package io.github.xxh3898.ourledger.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "our-ledger.auth.cloudflare")
public record CloudflareAccessProperties(
        String issuer,
        String jwkSetUri,
        String audience
) {

    public CloudflareAccessProperties validated() {
        requireText(issuer, "issuer");
        requireText(jwkSetUri, "jwk-set-uri");
        requireText(audience, "audience");
        return this;
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Cloudflare Access " + field + " 설정은 필수입니다.");
        }
    }
}
