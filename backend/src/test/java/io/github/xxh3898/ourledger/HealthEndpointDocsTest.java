package io.github.xxh3898.ourledger;

import io.github.xxh3898.ourledger.recurring.RecurringSchedulerOperationalState;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.restdocs.test.autoconfigure.AutoConfigureRestDocs;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedResponseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@AutoConfigureMockMvc
@AutoConfigureRestDocs
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = {
        "our-ledger.recurring.scheduler.enabled=true",
        "our-ledger.recurring.scheduler.initial-delay-ms=3600000"
})
class HealthEndpointDocsTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private Flyway flyway;

    @Autowired
    private Environment environment;

    @Autowired
    private RecurringSchedulerOperationalState recurringState;

    @Test
    void should_returnUp_when_healthEndpointIsRequested() throws Exception {
        mockMvc.perform(get("/actuator/health").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andDo(document(
                        "actuator-health",
                        responseFields(
                                fieldWithPath("groups").description("사용 가능한 상태 그룹"),
                                fieldWithPath("status").description("애플리케이션 상태")
                        )
                ));
    }

    @Test
    void should_applyMigrations_when_applicationStartsWithCleanDatabase() {
        assertThat(flyway.info().applied())
                .extracting(info -> info.getVersion().toString())
                .containsExactly("1", "2", "3", "4", "5", "6", "7", "8");
    }

    @Test
    void should_validateSchema_when_testProfileStarts() {
        assertThat(environment.getProperty("spring.jpa.hibernate.ddl-auto"))
                .isEqualTo("validate");
    }

    @Test
    void should_exposeRecurringOperationsWithoutChangingReadinessOrLiveness() throws Exception {
        Instant firstPoll = Instant.parse("2026-08-29T03:00:00Z");

        mockMvc.perform(get("/actuator/health/operations").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UNKNOWN"))
                .andExpect(jsonPath("$.components.recurringScheduler.details.enabled").value(true))
                .andExpect(jsonPath("$.components.recurringScheduler.details.pollCountSinceStart")
                        .value(0));

        recurringState.pollStarted(firstPoll);
        recurringState.pollFailed(firstPoll.plusSeconds(1));

        mockMvc.perform(get("/actuator/health/operations").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value("DOWN"))
                .andExpect(jsonPath("$.components.recurringScheduler.status").value("DOWN"))
                .andExpect(jsonPath("$.components.recurringScheduler.details.lastPollSucceeded")
                        .value(false));
        mockMvc.perform(get("/actuator/health/readiness").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.recurringScheduler").doesNotExist());
        mockMvc.perform(get("/actuator/health/liveness").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.recurringScheduler").doesNotExist());

        Instant recoveryPoll = firstPoll.plusSeconds(2);
        recurringState.pollStarted(recoveryPoll);
        recurringState.ruleFailed(recoveryPoll.plusSeconds(1));
        recurringState.pollSucceeded(recoveryPoll.plusSeconds(2), 1);

        mockMvc.perform(get("/actuator/health/operations").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"))
                .andExpect(jsonPath("$.components.recurringScheduler.status").value("UP"))
                .andExpect(jsonPath("$.components.recurringScheduler.details.lastPollRuleFailureCount")
                        .value(1))
                .andDo(document(
                        "actuator-operations-health",
                        relaxedResponseFields(
                                fieldWithPath("status").description("반복거래 scheduler poll 상태"),
                                subsectionWithPath("components.recurringScheduler")
                                        .description("비식별 반복거래 scheduler raw signal")
                        )
                ));
    }
}
