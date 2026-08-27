package io.github.xxh3898.ourledger.security;

import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.List;

public final class VerifiedIdentityAuthenticationToken extends AbstractAuthenticationToken {

    private final String email;

    public VerifiedIdentityAuthenticationToken(String email) {
        super(List.of(new SimpleGrantedAuthority("ROLE_VERIFIED_IDENTITY")));
        this.email = email;
        setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return null;
    }

    @Override
    public Object getPrincipal() {
        return email;
    }

    @Override
    public String getName() {
        return email;
    }

}
