package io.github.xxh3898.ourledger.security;

import io.github.xxh3898.ourledger.identity.EmailNormalizer;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.web.HeaderBearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration(proxyBeanMethods = false)
@Profile("!local & !test & !migration")
@EnableConfigurationProperties(CloudflareAccessProperties.class)
public class CloudflareAccessSecurityConfiguration {

    public static final String ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion";

    @Bean
    JwtDecoder cloudflareAccessJwtDecoder(CloudflareAccessProperties unvalidatedProperties) {
        CloudflareAccessProperties properties = unvalidatedProperties.validated();
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(properties.jwkSetUri()).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(properties.issuer());
        OAuth2TokenValidator<Jwt> audience = jwt -> jwt.getAudience().contains(properties.audience())
                ? OAuth2TokenValidatorResult.success()
                : failure("Cloudflare Access audience가 일치하지 않습니다.");
        OAuth2TokenValidator<Jwt> email = jwt -> isValidEmailClaim(jwt)
                ? OAuth2TokenValidatorResult.success()
                : failure("Cloudflare Access email claim이 필요합니다.");

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience, email));
        return decoder;
    }

    @Bean
    SecurityFilterChain cloudflareAccessSecurityFilterChain(
            HttpSecurity http,
            JwtDecoder cloudflareAccessJwtDecoder,
            CurrentHouseholdService currentHouseholdService
    ) throws Exception {
        JsonAuthenticationEntryPoint authenticationEntryPoint = new JsonAuthenticationEntryPoint();
        JsonAccessDeniedHandler accessDeniedHandler = new JsonAccessDeniedHandler();

        http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health", "/actuator/health/**").permitAll()
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().denyAll()
                )
                .csrf(csrf -> csrf
                        .spa()
                        .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                )
                .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(authenticationEntryPoint)
                        .accessDeniedHandler(accessDeniedHandler)
                )
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .bearerTokenResolver(new HeaderBearerTokenResolver(ACCESS_JWT_HEADER))
                        .authenticationEntryPoint(authenticationEntryPoint)
                        .jwt(jwt -> jwt
                                .decoder(cloudflareAccessJwtDecoder)
                                .jwtAuthenticationConverter(token ->
                                        new VerifiedIdentityAuthenticationToken(
                                                EmailNormalizer.normalize(token.getClaimAsString("email"))
                                        )
                                )
                        )
                )
                .addFilterAfter(
                        new InternalIdentityAuthorizationFilter(currentHouseholdService),
                        BearerTokenAuthenticationFilter.class
                );

        return http.build();
    }

    private boolean isValidEmailClaim(Jwt jwt) {
        try {
            EmailNormalizer.normalize(jwt.getClaimAsString("email"));
            return true;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private OAuth2TokenValidatorResult failure(String description) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", description, null)
        );
    }
}
