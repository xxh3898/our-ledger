package io.github.xxh3898.ourledger.recurring;

import org.junit.jupiter.api.Test;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class RecurringSchedulerHealthIndicatorTest {

    private static final Instant PROCESS_STARTED_AT = Instant.parse("2026-08-29T00:00:00Z");
    private static final Instant POLL_STARTED_AT = Instant.parse("2026-08-29T00:01:00Z");

    @Test
    void should_reportUnknownWithSafeDetails_when_pollHasNotRun() {
        RecurringSchedulerOperationalState state = state(false);

        Health health = new RecurringSchedulerHealthIndicator(state).health();

        assertThat(health.getStatus()).isEqualTo(Status.UNKNOWN);
        assertThat(health.getDetails())
                .hasSize(12)
                .containsEntry("enabled", false)
                .containsEntry("processStartedAt", PROCESS_STARTED_AT.toString())
                .containsEntry("pollCountSinceStart", 0L)
                .containsEntry("lastAdvancedOccurrenceCount", 0)
                .containsEntry("lastPollRuleFailureCount", 0L)
                .containsEntry("totalRuleFailureCountSinceStart", 0L)
                .containsEntry("consecutivePollExecutionFailures", 0L)
                .containsEntry("lastPollStartedAt", null)
                .containsEntry("lastPollCompletedAt", null)
                .containsEntry("lastPollSucceeded", null)
                .containsEntry("lastPollExecutionFailureAt", null)
                .containsEntry("lastRuleFailureAt", null);
    }

    @Test
    void should_reportUpDespiteRuleFailure_when_pollCompletesNormally() {
        RecurringSchedulerOperationalState state = state(true);
        state.pollStarted(POLL_STARTED_AT);
        state.ruleFailed(POLL_STARTED_AT.plusSeconds(1));
        state.pollSucceeded(POLL_STARTED_AT.plusSeconds(2), 2);

        Health health = new RecurringSchedulerHealthIndicator(state).health();

        assertThat(health.getStatus()).isEqualTo(Status.UP);
        assertThat(health.getDetails())
                .containsEntry("lastPollSucceeded", true)
                .containsEntry("lastPollRuleFailureCount", 1L)
                .containsEntry("lastAdvancedOccurrenceCount", 2);
    }

    @Test
    void should_reportDownWithoutExceptionDetails_when_topLevelPollFails() {
        RecurringSchedulerOperationalState state = state(true);
        state.pollStarted(POLL_STARTED_AT);
        state.pollFailed(POLL_STARTED_AT.plusSeconds(1));

        Health health = new RecurringSchedulerHealthIndicator(state).health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
        assertThat(health.getDetails())
                .containsEntry("lastPollSucceeded", false)
                .doesNotContainKeys("error", "exception", "message", "stackTrace");
    }

    private RecurringSchedulerOperationalState state(boolean enabled) {
        return new RecurringSchedulerOperationalState(
                Clock.fixed(PROCESS_STARTED_AT, ZoneOffset.UTC),
                enabled
        );
    }
}
