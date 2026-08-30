package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

public final class InternalIdentityAuthorizationFilter extends OncePerRequestFilter {

    private final CurrentHouseholdService currentHouseholdService;

    public InternalIdentityAuthorizationFilter(CurrentHouseholdService currentHouseholdService) {
        this.currentHouseholdService = currentHouseholdService;
    }

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
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication instanceof VerifiedIdentityAuthenticationToken verifiedIdentity) {
            try {
                CurrentHousehold currentHousehold = currentHouseholdService.resolve(verifiedIdentity.getName());
                HouseholdAuthenticationToken householdAuthentication =
                        new HouseholdAuthenticationToken(currentHousehold);
                householdAuthentication.setDetails(verifiedIdentity.getDetails());
                SecurityContextHolder.getContext().setAuthentication(householdAuthentication);
            } catch (IdentityAccessDeniedException exception) {
                SecurityContextHolder.clearContext();
                SecurityJsonResponseWriter.write(
                        response,
                        HttpServletResponse.SC_FORBIDDEN,
                        exception.getErrorCode()
                );
                return;
            }
        } else if (authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof HouseholdAuthenticationToken)
                && !(authentication instanceof AnonymousAuthenticationToken)) {
            SecurityContextHolder.clearContext();
            SecurityJsonResponseWriter.write(
                    response,
                    HttpServletResponse.SC_FORBIDDEN,
                    ApiErrorCode.ACCESS_DENIED
            );
            return;
        }
        filterChain.doFilter(request, response);
    }
}
