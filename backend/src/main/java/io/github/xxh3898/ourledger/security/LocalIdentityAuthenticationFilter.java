package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.identity.EmailNormalizer;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

public final class LocalIdentityAuthenticationFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Our-Ledger-Local-Identity";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(request.getContextPath() + "/api/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String header = request.getHeader(HEADER_NAME);
        if (header != null && !header.isBlank()) {
            try {
                String email = EmailNormalizer.normalize(header);
                SecurityContextHolder.getContext().setAuthentication(
                        new VerifiedIdentityAuthenticationToken(email)
                );
            } catch (IllegalArgumentException ignored) {
                SecurityContextHolder.clearContext();
            }
        }
        filterChain.doFilter(request, response);
    }
}
