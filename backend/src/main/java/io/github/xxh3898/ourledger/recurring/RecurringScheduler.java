package io.github.xxh3898.ourledger.recurring;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
@Profile("!migration & !bootstrap")
@ConditionalOnProperty(
        prefix = "our-ledger.recurring.scheduler",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class RecurringScheduler {

    private final RecurringGenerationService generationService;
    private final Clock clock;
    private final RecurringSchedulerOperationalState operationalState;

    public RecurringScheduler(
            RecurringGenerationService generationService,
            Clock clock,
            RecurringSchedulerOperationalState operationalState
    ) {
        this.generationService = generationService;
        this.clock = clock;
        this.operationalState = operationalState;
    }

    @Scheduled(
            fixedDelayString = "${our-ledger.recurring.scheduler.poll-delay-ms:60000}",
            initialDelayString = "${our-ledger.recurring.scheduler.initial-delay-ms:0}"
    )
    void generateDueOccurrences() {
        java.time.Instant startedAt = clock.instant();
        operationalState.pollStarted(startedAt);
        try {
            int advanced = generationService.generateDue(startedAt);
            operationalState.pollSucceeded(clock.instant(), advanced);
        } catch (RuntimeException exception) {
            operationalState.pollFailed(clock.instant());
            throw exception;
        }
    }
}
