package io.github.xxh3898.ourledger.recurring;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RecurringGenerationServiceTest {

    private static final Instant NOW = Instant.parse("2026-08-29T02:00:00Z");

    @Test
    void should_recordFailureAndContinueNextRule_when_oneRuleFails() {
        RecurringTransactionRepository repository = mock(RecurringTransactionRepository.class);
        RecurringOccurrenceProcessor processor = mock(RecurringOccurrenceProcessor.class);
        RecurringSchedulerOperationalState state = mock(RecurringSchedulerOperationalState.class);
        when(repository.findDueIds(NOW, 1)).thenReturn(List.of(1L, 2L));
        when(processor.generateOne(1L, NOW))
                .thenThrow(new IllegalStateException("synthetic rule failure"));
        when(processor.generateOne(2L, NOW))
                .thenReturn(RecurringOccurrenceProcessor.Result.GENERATED);
        RecurringGenerationService service = new RecurringGenerationService(
                repository, processor, 100, state);

        assertThat(service.generateDue(NOW, 1)).isEqualTo(1);

        verify(state).ruleFailed(NOW);
        verify(processor).generateOne(2L, NOW);
    }

    @Test
    void should_countEveryFailure_when_multipleRulesFail() {
        RecurringTransactionRepository repository = mock(RecurringTransactionRepository.class);
        RecurringOccurrenceProcessor processor = mock(RecurringOccurrenceProcessor.class);
        RecurringSchedulerOperationalState state = mock(RecurringSchedulerOperationalState.class);
        when(repository.findDueIds(NOW, 3)).thenReturn(List.of(1L, 2L));
        when(processor.generateOne(1L, NOW)).thenThrow(new IllegalStateException("first"));
        when(processor.generateOne(2L, NOW)).thenThrow(new IllegalArgumentException("second"));
        RecurringGenerationService service = new RecurringGenerationService(
                repository, processor, 100, state);

        assertThat(service.generateDue(NOW, 3)).isZero();

        verify(state, times(2)).ruleFailed(NOW);
    }
}
