package io.github.xxh3898.ourledger.security;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.List;

public final class HouseholdAuthenticationToken extends AbstractAuthenticationToken {

    private final CurrentHousehold currentHousehold;

    public HouseholdAuthenticationToken(CurrentHousehold currentHousehold) {
        super(List.of(new SimpleGrantedAuthority("ROLE_HOUSEHOLD_MEMBER")));
        this.currentHousehold = currentHousehold;
        setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return null;
    }

    @Override
    public CurrentHousehold getPrincipal() {
        return currentHousehold;
    }

    @Override
    public String getName() {
        return currentHousehold.email();
    }
}
