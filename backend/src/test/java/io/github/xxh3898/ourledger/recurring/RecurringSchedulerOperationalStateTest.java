package io.github.xxh3898.ourledger.recurring;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;

class RecurringSchedulerOperationalStateTest {

    private static final Instant PROCESS_STARTED_AT = Instant.parse("2026-08-29T00:00:00Z");
    private static final Instant POLL_STARTED_AT = Instant.parse("2026-08-29T00:01:00Z");

    @Test
    void should_reportNotYetRun_when_processStarts() {
        RecurringSchedulerOperationalState state = state(true);

        assertThat(state.snapshot()).isEqualTo(new RecurringSchedulerOperationalState.Snapshot(
                true,
                PROCESS_STARTED_AT,
                0,
                null,
                null,
                null,
                0,
                0,
                0,
                0,
                null,
                null
        ));
    }

    @Test
    void should_recordSuccessfulPollAndRuleFailures_when_pollCompletes() {
        RecurringSchedulerOperationalState state = state(true);
        Instant firstRuleFailure = POLL_STARTED_AT.plusSeconds(1);
        Instant secondRuleFailure = POLL_STARTED_AT.plusSeconds(2);
        Instant completedAt = POLL_STARTED_AT.plusSeconds(3);

        state.pollStarted(POLL_STARTED_AT);
        state.ruleFailed(firstRuleFailure);
        state.ruleFailed(secondRuleFailure);
        state.pollSucceeded(completedAt, 4);

        assertThat(state.snapshot()).isEqualTo(new RecurringSchedulerOperationalState.Snapshot(
                true,
                PROCESS_STARTED_AT,
                1,
                POLL_STARTED_AT,
                completedAt,
                true,
                4,
                2,
                2,
                0,
                null,
                secondRuleFailure
        ));
    }

    @Test
    void should_resetConsecutiveFailures_when_laterPollSucceeds() {
        RecurringSchedulerOperationalState state = state(true);
        Instant firstFailure = POLL_STARTED_AT.plusSeconds(1);
        Instant secondStart = POLL_STARTED_AT.plusSeconds(2);
        Instant secondFailure = POLL_STARTED_AT.plusSeconds(3);
        Instant recoveryStart = POLL_STARTED_AT.plusSeconds(4);
        Instant recoveryCompleted = POLL_STARTED_AT.plusSeconds(5);

        state.pollStarted(POLL_STARTED_AT);
        state.pollFailed(firstFailure);
        state.pollStarted(secondStart);
        state.pollFailed(secondFailure);

        assertThat(state.snapshot().consecutivePollExecutionFailures()).isEqualTo(2);

        state.pollStarted(recoveryStart);
        state.pollSucceeded(recoveryCompleted, 1);

        RecurringSchedulerOperationalState.Snapshot snapshot = state.snapshot();
        assertThat(snapshot.pollCountSinceStart()).isEqualTo(3);
        assertThat(snapshot.lastPollSucceeded()).isTrue();
        assertThat(snapshot.lastAdvancedOccurrenceCount()).isEqualTo(1);
        assertThat(snapshot.lastPollRuleFailureCount()).isZero();
        assertThat(snapshot.consecutivePollExecutionFailures()).isZero();
        assertThat(snapshot.lastPollExecutionFailureAt()).isEqualTo(secondFailure);
    }

    @Test
    void should_exposeDisabledStateWithoutInventingPollSuccess_when_schedulerIsDisabled() {
        RecurringSchedulerOperationalState.Snapshot snapshot = state(false).snapshot();

        assertThat(snapshot.enabled()).isFalse();
        assertThat(snapshot.pollCountSinceStart()).isZero();
        assertThat(snapshot.lastPollSucceeded()).isNull();
    }

    @Test
    void should_keepCountersConsistent_when_failuresAndSnapshotsAreConcurrent() throws Exception {
        RecurringSchedulerOperationalState state = state(true);
        state.pollStarted(POLL_STARTED_AT);
        ExecutorService executor = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Void>> writers = java.util.stream.IntStream.range(0, 8)
                    .mapToObj(worker -> (Callable<Void>) () -> {
                        for (int event = 0; event < 250; event++) {
                            state.ruleFailed(POLL_STARTED_AT.plusSeconds(worker + 1L));
                        }
                        return null;
                    })
                    .toList();
            Future<Void> reader = executor.submit(() -> {
                for (int read = 0; read < 1_000; read++) {
                    RecurringSchedulerOperationalState.Snapshot snapshot = state.snapshot();
                    assertThat(snapshot.lastPollRuleFailureCount())
                            .isBetween(0L, snapshot.totalRuleFailureCountSinceStart());
                }
                return null;
            });

            for (Future<Void> writer : executor.invokeAll(writers)) {
                writer.get();
            }
            reader.get();
            state.pollSucceeded(POLL_STARTED_AT.plusSeconds(20), 0);

            assertThat(state.snapshot().lastPollRuleFailureCount()).isEqualTo(2_000);
            assertThat(state.snapshot().totalRuleFailureCountSinceStart()).isEqualTo(2_000);
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void should_exposeOnlyNonIdentifyingSnapshotFields_when_snapshotContractIsInspected() {
        assertThat(Arrays.stream(RecurringSchedulerOperationalState.Snapshot.class
                        .getRecordComponents())
                .map(component -> component.getName()))
                .containsExactly(
                        "enabled",
                        "processStartedAt",
                        "pollCountSinceStart",
                        "lastPollStartedAt",
                        "lastPollCompletedAt",
                        "lastPollSucceeded",
                        "lastAdvancedOccurrenceCount",
                        "lastPollRuleFailureCount",
                        "totalRuleFailureCountSinceStart",
                        "consecutivePollExecutionFailures",
                        "lastPollExecutionFailureAt",
                        "lastRuleFailureAt"
                );
    }

    private RecurringSchedulerOperationalState state(boolean enabled) {
        return new RecurringSchedulerOperationalState(
                Clock.fixed(PROCESS_STARTED_AT, ZoneOffset.UTC),
                enabled
        );
    }
}
