package io.github.xxh3898.ourledger.bootstrap;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "our-ledger.bootstrap")
public record HouseholdBootstrapProperties(
        boolean enabled,
        String householdName,
        Person owner,
        Person member
) {

    public HouseholdBootstrapRequest toRequest() {
        if (!enabled) {
            throw new IllegalStateException("비활성 bootstrap 설정은 실행할 수 없습니다.");
        }
        if (owner == null || member == null) {
            throw new IllegalArgumentException("owner와 member bootstrap 설정은 필수입니다.");
        }
        return new HouseholdBootstrapRequest(
                householdName,
                owner.email(),
                owner.displayName(),
                member.email(),
                member.displayName()
        );
    }

    public record Person(String email, String displayName) {
    }
}
