package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapRequest;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapResult;
import io.github.xxh3898.ourledger.bootstrap.HouseholdBootstrapService;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.household.HouseholdRole;
import io.github.xxh3898.ourledger.identity.User;
import io.github.xxh3898.ourledger.identity.UserRepository;
import io.github.xxh3898.ourledger.security.LocalIdentityAuthenticationFilter;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.http.HttpStatus.NO_CONTENT;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import({TestcontainersConfiguration.class, AuthHouseholdDocsTest.MutationFixtureConfiguration.class})
@SpringBootTest
class AuthHouseholdDocsTest {

    private static final String LOCAL_IDENTITY_HEADER =
            LocalIdentityAuthenticationFilter.HEADER_NAME;

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

    private Long currentHouseholdId;

    @BeforeEach
    void provisionHousehold() {
        householdMemberRepository.deleteAllInBatch();
        householdRepository.deleteAllInBatch();
        userRepository.deleteAllInBatch();
        HouseholdBootstrapResult result = householdBootstrapService.provision(new HouseholdBootstrapRequest(
                "테스트 Household",
                "owner@example.test",
                "Owner",
                "member@example.test",
                "Member"
        ));
        currentHouseholdId = result.householdId();
    }

    @Test
    void should_documentCurrentUser_when_localIdentityMapsToMembership() throws Exception {
        mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, " OWNER@EXAMPLE.TEST ")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(cookie().exists("XSRF-TOKEN"))
                .andExpect(header().exists("X-XSRF-TOKEN"))
                .andExpect(jsonPath("$.email").value("owner@example.test"))
                .andExpect(jsonPath("$.displayName").value("Owner"))
                .andExpect(jsonPath("$.householdName").value("테스트 Household"))
                .andExpect(jsonPath("$.role").value("OWNER"))
                .andDo(document(
                        "current-user",
                        responseFields(
                                fieldWithPath("userId").description("내부 User ID"),
                                fieldWithPath("email").description("정규화된 User email"),
                                fieldWithPath("displayName").description("표시명"),
                                fieldWithPath("householdId").description("현재 Household ID"),
                                fieldWithPath("householdName").description("현재 Household 이름"),
                                fieldWithPath("role").description("현재 Household role")
                        )
                ));
    }

    @Test
    void should_documentCurrentHousehold_withoutUsingClientHouseholdId() throws Exception {
        User otherUser = userRepository.saveAndFlush(User.create("other@example.test", "Other"));
        Household otherHousehold = householdRepository.saveAndFlush(Household.create("다른 Household"));
        householdMemberRepository.saveAndFlush(
                HouseholdMember.create(otherHousehold, otherUser, HouseholdRole.OWNER));

        mockMvc.perform(get("/api/v1/households/current")
                        .queryParam("householdId", otherHousehold.getId().toString())
                        .header(LOCAL_IDENTITY_HEADER, "owner@example.test")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.householdId").value(currentHouseholdId))
                .andExpect(jsonPath("$.name").value("테스트 Household"))
                .andExpect(jsonPath("$.baseCurrency").value("KRW"))
                .andExpect(jsonPath("$.timezone").value("Asia/Seoul"))
                .andExpect(jsonPath("$.members.length()").value(2))
                .andExpect(jsonPath("$.members[0].displayName").value("Owner"))
                .andExpect(jsonPath("$.members[1].displayName").value("Member"))
                .andDo(document(
                        "current-household",
                        responseFields(
                                fieldWithPath("householdId").description("현재 Household ID"),
                                fieldWithPath("name").description("Household 이름"),
                                fieldWithPath("baseCurrency").description("기준 통화"),
                                fieldWithPath("timezone").description("Household timezone"),
                                fieldWithPath("members[].userId").description("Member의 내부 User ID"),
                                fieldWithPath("members[].displayName").description("Member 표시명"),
                                fieldWithPath("members[].role").description("Member role")
                        )
                ));
    }

    @Test
    void should_returnUnauthorized_when_authenticationIsMissing() throws Exception {
        mockMvc.perform(get("/api/v1/me").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void should_ignoreArbitraryEmailHeader_when_localIdentityHeaderIsMissing() throws Exception {
        mockMvc.perform(get("/api/v1/me")
                        .header("X-User-Email", "owner@example.test")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void should_returnForbidden_when_internalUserIsNotRegistered() throws Exception {
        mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, "unknown@example.test")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("USER_NOT_REGISTERED"));
    }

    @Test
    void should_returnForbidden_when_internalUserIsDisabled() throws Exception {
        User owner = userRepository.findByEmail("owner@example.test").orElseThrow();
        owner.disable();
        userRepository.saveAndFlush(owner);

        mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, "owner@example.test")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("USER_DISABLED"));
    }

    @Test
    void should_returnForbidden_when_internalUserHasNoMembership() throws Exception {
        userRepository.saveAndFlush(User.create("solo@example.test", "Solo"));

        mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, "solo@example.test")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("HOUSEHOLD_MEMBERSHIP_REQUIRED"));
    }

    @Test
    void should_rejectUnsafeRequest_when_csrfTokenIsMissing() throws Exception {
        mockMvc.perform(post("/api/v1/security-test-mutation")
                        .header(LOCAL_IDENTITY_HEADER, "owner@example.test"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_TOKEN_INVALID"));
    }

    @Test
    void should_allowUnsafeRequest_when_csrfTokenIsValid() throws Exception {
        Cookie csrfCookie = mockMvc.perform(get("/api/v1/me")
                        .header(LOCAL_IDENTITY_HEADER, "owner@example.test"))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getCookie("XSRF-TOKEN");

        mockMvc.perform(post("/api/v1/security-test-mutation")
                        .header(LOCAL_IDENTITY_HEADER, "owner@example.test")
                        .header("X-XSRF-TOKEN", csrfCookie.getValue())
                        .cookie(csrfCookie))
                .andExpect(status().isNoContent());
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class MutationFixtureConfiguration {

        @Bean
        MutationFixtureController mutationFixtureController() {
            return new MutationFixtureController();
        }
    }

    @RestController
    static class MutationFixtureController {

        @PostMapping("/api/v1/security-test-mutation")
        @ResponseStatus(NO_CONTENT)
        void mutate() {
        }
    }
}
