package io.github.xxh3898.ourledger;

import com.sun.net.httpserver.HttpServer;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.CloudflareAccessSecurityConfiguration;
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.io.IOException;
import java.math.BigInteger;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("production")
@AutoConfigureMockMvc
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class CloudflareAccessSecurityIntegrationTest {

    private static final String ISSUER = "https://test-team.cloudflareaccess.com";
    private static final String AUDIENCE = "test-application-audience";
    private static final String KEY_ID = "test-key";
    private static final JwtFixture JWT_FIXTURE = JwtFixture.create();
    private static final TestJwkServer JWK_SERVER = new TestJwkServer(JWT_FIXTURE.publicKey());

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private HouseholdRepository householdRepository;

    @Autowired
    private HouseholdMemberRepository householdMemberRepository;

    @Autowired
    private HouseholdBootstrapService householdBootstrapService;

    @Autowired
    private FilterChainProxy filterChainProxy;

    @DynamicPropertySource
    static void cloudflareProperties(DynamicPropertyRegistry registry) {
        JWK_SERVER.start();
        registry.add("our-ledger.auth.cloudflare.issuer", () -> ISSUER);
        registry.add("our-ledger.auth.cloudflare.jwk-set-uri", JWK_SERVER::jwkSetUri);
        registry.add("our-ledger.auth.cloudflare.audience", () -> AUDIENCE);
    }

    @AfterAll
    static void stopJwkServer() {
        JWK_SERVER.stop();
    }

    @BeforeEach
    void provisionHousehold() {
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
        householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "테스트 Household",
                "owner@example.test",
                "Owner",
                "member@example.test",
                "Member"
        ));
    }

    @Test
    void should_authenticate_when_signatureIssuerAudienceTimeAndEmailAreValid() throws Exception {
        String token = JWT_FIXTURE.token(
                ISSUER,
                AUDIENCE,
                " OWNER@EXAMPLE.TEST ",
                Instant.now().minusSeconds(5),
                Instant.now().plusSeconds(300),
                JWT_FIXTURE.privateKey()
        );

        mockMvc.perform(get("/api/v1/me")
                        .header(CloudflareAccessSecurityConfiguration.ACCESS_JWT_HEADER, token)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("owner@example.test"))
                .andExpect(jsonPath("$.role").value("OWNER"));
    }

    @Test
    void should_keepHealthPublic_when_accessJwtIsMissing() throws Exception {
        mockMvc.perform(get("/actuator/health").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void should_requireAuthentication_when_undeclaredApiEndpointIsRequested() throws Exception {
        mockMvc.perform(get("/api/v1/not-declared").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void should_rejectToken_when_signatureIsInvalid() throws Exception {
        String token = JWT_FIXTURE.token(
                ISSUER,
                AUDIENCE,
                "owner@example.test",
                Instant.now().minusSeconds(5),
                Instant.now().plusSeconds(300),
                JwtFixture.newKeyPair().getPrivate()
        );

        assertUnauthorized(token);
    }

    @Test
    void should_rejectToken_when_issuerIsInvalid() throws Exception {
        assertUnauthorized(JWT_FIXTURE.validToken("https://other.cloudflareaccess.com", AUDIENCE));
    }

    @Test
    void should_rejectToken_when_audienceIsInvalid() throws Exception {
        assertUnauthorized(JWT_FIXTURE.validToken(ISSUER, "other-audience"));
    }

    @Test
    void should_rejectToken_when_tokenIsExpired() throws Exception {
        String token = JWT_FIXTURE.token(
                ISSUER,
                AUDIENCE,
                "owner@example.test",
                Instant.now().minusSeconds(300),
                Instant.now().minusSeconds(120),
                JWT_FIXTURE.privateKey()
        );

        assertUnauthorized(token);
    }

    @Test
    void should_rejectToken_when_notBeforeIsInFuture() throws Exception {
        String token = JWT_FIXTURE.token(
                ISSUER,
                AUDIENCE,
                "owner@example.test",
                Instant.now().plusSeconds(120),
                Instant.now().plusSeconds(300),
                JWT_FIXTURE.privateKey()
        );

        assertUnauthorized(token);
    }

    @Test
    void should_rejectToken_when_emailClaimIsMissing() throws Exception {
        String token = JWT_FIXTURE.tokenWithoutEmail(
                ISSUER,
                AUDIENCE,
                Instant.now().minusSeconds(5),
                Instant.now().plusSeconds(300)
        );

        assertUnauthorized(token);
    }

    @Test
    void should_returnForbidden_when_validIdentityHasNoInternalUser() throws Exception {
        mockMvc.perform(authenticatedGet(JWT_FIXTURE.validToken(
                        ISSUER, AUDIENCE, "unknown@example.test")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("USER_NOT_REGISTERED"));
    }

    @Test
    void should_returnForbidden_when_validIdentityMapsToDisabledUser() throws Exception {
        User owner = userRepository.findByEmail("owner@example.test").orElseThrow();
        owner.disable();
        userRepository.saveAndFlush(owner);

        mockMvc.perform(authenticatedGet(JWT_FIXTURE.validToken(
                        ISSUER, AUDIENCE, "owner@example.test")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("USER_DISABLED"));
    }

    @Test
    void should_returnForbidden_when_validIdentityHasNoHouseholdMembership() throws Exception {
        userRepository.saveAndFlush(User.create("solo@example.test", "Solo"));

        mockMvc.perform(authenticatedGet(JWT_FIXTURE.validToken(
                        ISSUER, AUDIENCE, "solo@example.test")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("HOUSEHOLD_MEMBERSHIP_REQUIRED"));
    }

    @Test
    void should_ignoreAuthorizationAndLocalIdentityHeaders_when_cloudflareHeaderIsMissing() throws Exception {
        String token = JWT_FIXTURE.validToken(ISSUER, AUDIENCE);

        mockMvc.perform(get("/api/v1/me")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                        .header(LocalIdentityAuthenticationFilter.HEADER_NAME, "owner@example.test"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void should_excludeLocalIdentityFilter_when_productionProfileIsActive() {
        assertThat(filterChainProxy.getFilters("/api/v1/me"))
                .noneMatch(LocalIdentityAuthenticationFilter.class::isInstance);
    }

    private void assertUnauthorized(String token) throws Exception {
        mockMvc.perform(authenticatedGet(token))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder authenticatedGet(
            String token
    ) {
        return get("/api/v1/me")
                .header(CloudflareAccessSecurityConfiguration.ACCESS_JWT_HEADER, token)
                .accept(MediaType.APPLICATION_JSON);
    }

    private record JwtFixture(KeyPair keyPair) {

        static JwtFixture create() {
            return new JwtFixture(newKeyPair());
        }

        static KeyPair newKeyPair() {
            try {
                KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
                generator.initialize(2048);
                return generator.generateKeyPair();
            } catch (Exception exception) {
                throw new IllegalStateException("test RSA key를 만들 수 없습니다.", exception);
            }
        }

        RSAPublicKey publicKey() {
            return (RSAPublicKey) keyPair.getPublic();
        }

        PrivateKey privateKey() {
            return keyPair.getPrivate();
        }

        String validToken(String issuer, String audience) {
            return validToken(issuer, audience, "owner@example.test");
        }

        String validToken(String issuer, String audience, String email) {
            return token(
                    issuer,
                    audience,
                    email,
                    Instant.now().minusSeconds(5),
                    Instant.now().plusSeconds(300),
                    privateKey()
            );
        }

        String token(
                String issuer,
                String audience,
                String email,
                Instant notBefore,
                Instant expiresAt,
                PrivateKey signingKey
        ) {
            String emailClaim = ",\"email\":\"" + email + "\"";
            return sign(payload(issuer, audience, notBefore, expiresAt, emailClaim), signingKey);
        }

        String tokenWithoutEmail(
                String issuer,
                String audience,
                Instant notBefore,
                Instant expiresAt
        ) {
            return sign(payload(issuer, audience, notBefore, expiresAt, ""), privateKey());
        }

        private String payload(
                String issuer,
                String audience,
                Instant notBefore,
                Instant expiresAt,
                String additionalClaims
        ) {
            return "{\"iss\":\"" + issuer
                    + "\",\"aud\":[\"" + audience
                    + "\"],\"sub\":\"test-user\",\"iat\":" + Instant.now().minusSeconds(5).getEpochSecond()
                    + ",\"nbf\":" + notBefore.getEpochSecond()
                    + ",\"exp\":" + expiresAt.getEpochSecond()
                    + additionalClaims + "}";
        }

        private String sign(String payload, PrivateKey signingKey) {
            try {
                Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
                String header = encoder.encodeToString(
                        ("{\"alg\":\"RS256\",\"kid\":\"" + KEY_ID + "\",\"typ\":\"JWT\"}")
                                .getBytes(StandardCharsets.UTF_8)
                );
                String encodedPayload = encoder.encodeToString(payload.getBytes(StandardCharsets.UTF_8));
                String signingInput = header + "." + encodedPayload;
                Signature signature = Signature.getInstance("SHA256withRSA");
                signature.initSign(signingKey);
                signature.update(signingInput.getBytes(StandardCharsets.US_ASCII));
                return signingInput + "." + encoder.encodeToString(signature.sign());
            } catch (Exception exception) {
                throw new IllegalStateException("test JWT를 만들 수 없습니다.", exception);
            }
        }
    }

    private static final class TestJwkServer {

        private final RSAPublicKey publicKey;
        private HttpServer server;

        private TestJwkServer(RSAPublicKey publicKey) {
            this.publicKey = publicKey;
        }

        synchronized void start() {
            if (server != null) {
                return;
            }
            try {
                server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
                server.createContext("/jwks", exchange -> {
                    byte[] body = jwkSet().getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type", MediaType.APPLICATION_JSON_VALUE);
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                    exchange.close();
                });
                server.start();
            } catch (IOException exception) {
                throw new IllegalStateException("test JWK server를 시작할 수 없습니다.", exception);
            }
        }

        synchronized void stop() {
            if (server != null) {
                server.stop(0);
                server = null;
            }
        }

        String jwkSetUri() {
            return "http://127.0.0.1:" + server.getAddress().getPort() + "/jwks";
        }

        private String jwkSet() {
            return "{\"keys\":[{\"kty\":\"RSA\",\"kid\":\"" + KEY_ID
                    + "\",\"use\":\"sig\",\"alg\":\"RS256\",\"n\":\""
                    + unsignedBase64(publicKey.getModulus())
                    + "\",\"e\":\"" + unsignedBase64(publicKey.getPublicExponent()) + "\"}]}";
        }

        private String unsignedBase64(BigInteger value) {
            byte[] bytes = value.toByteArray();
            if (bytes.length > 1 && bytes[0] == 0) {
                bytes = Arrays.copyOfRange(bytes, 1, bytes.length);
            }
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        }
    }
}
