package io.github.xxh3898.ourledger.recurring;

import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RecurringSchedulerTest {

    private static final Instant NOW = Instant.parse("2026-08-29T01:00:00Z");

    @Test
    void should_recordAdvancedCount_when_generationCompletes() {
        RecurringGenerationService generationService = mock(RecurringGenerationService.class);
        RecurringSchedulerOperationalState state = state();
        when(generationService.generateDue(NOW)).thenReturn(3);
        RecurringScheduler scheduler = scheduler(generationService, state);

        scheduler.generateDueOccurrences();

        verify(generationService).generateDue(NOW);
        RecurringSchedulerOperationalState.Snapshot snapshot = state.snapshot();
        assertThat(snapshot.lastPollSucceeded()).isTrue();
        assertThat(snapshot.lastAdvancedOccurrenceCount()).isEqualTo(3);
        assertThat(snapshot.consecutivePollExecutionFailures()).isZero();
    }

    @Test
    void should_recordFailureAndRethrowSameException_when_generationFails() {
        RecurringGenerationService generationService = mock(RecurringGenerationService.class);
        RecurringSchedulerOperationalState state = state();
        RuntimeException failure = new IllegalStateException("synthetic generation failure");
        when(generationService.generateDue(NOW)).thenThrow(failure);
        RecurringScheduler scheduler = scheduler(generationService, state);

        assertThatThrownBy(scheduler::generateDueOccurrences).isSameAs(failure);

        RecurringSchedulerOperationalState.Snapshot snapshot = state.snapshot();
        assertThat(snapshot.lastPollSucceeded()).isFalse();
        assertThat(snapshot.consecutivePollExecutionFailures()).isEqualTo(1);
        assertThat(snapshot.lastPollExecutionFailureAt()).isEqualTo(NOW);
    }

    private RecurringScheduler scheduler(
            RecurringGenerationService generationService,
            RecurringSchedulerOperationalState state
    ) {
        return new RecurringScheduler(
                generationService,
                Clock.fixed(NOW, ZoneOffset.UTC),
                state
        );
    }

    private RecurringSchedulerOperationalState state() {
        return new RecurringSchedulerOperationalState(
                Clock.fixed(NOW.minusSeconds(60), ZoneOffset.UTC),
                true
        );
    }
}
