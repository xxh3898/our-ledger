package io.github.xxh3898.ourledger.recurring;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Clock;

@Component
@ConditionalOnProperty(
        prefix = "our-ledger.recurring.scheduler",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class RecurringScheduler {

    private final RecurringGenerationService generationService;
    private final Clock clock;

    public RecurringScheduler(RecurringGenerationService generationService, Clock clock) {
        this.generationService = generationService;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${our-ledger.recurring.scheduler.poll-delay-ms:60000}")
    void generateDueOccurrences() {
        generationService.generateDue(clock.instant());
    }
}
