package io.github.xxh3898.ourledger.recurring;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.List;

@Service
public class RecurringGenerationService {

    private static final Logger log = LoggerFactory.getLogger(RecurringGenerationService.class);

    private final RecurringTransactionRepository recurringRepository;
    private final RecurringOccurrenceProcessor occurrenceProcessor;
    private final int batchSize;

    public RecurringGenerationService(
            RecurringTransactionRepository recurringRepository,
            RecurringOccurrenceProcessor occurrenceProcessor,
            @Value("${our-ledger.recurring.scheduler.batch-size:100}") int batchSize
    ) {
        this.recurringRepository = recurringRepository;
        this.occurrenceProcessor = occurrenceProcessor;
        this.batchSize = batchSize;
    }

    public int generateDue(Instant now) {
        return generateDue(now, batchSize);
    }

    public int generateDue(Instant now, int maximumOccurrences) {
        if (maximumOccurrences <= 0) {
            throw new IllegalArgumentException("maximumOccurrences는 1 이상이어야 합니다.");
        }
        List<Long> initialIds = recurringRepository.findDueIds(now, maximumOccurrences);
        ArrayDeque<Long> pending = new ArrayDeque<>(initialIds);
        int advanced = 0;
        while (!pending.isEmpty() && advanced < maximumOccurrences) {
            Long recurringId = pending.removeFirst();
            try {
                RecurringOccurrenceProcessor.Result result =
                        occurrenceProcessor.generateOne(recurringId, now);
                if (result.cursorAdvanced()) {
                    advanced++;
                    if (advanced < maximumOccurrences) {
                        pending.addLast(recurringId);
                    }
                }
            } catch (RuntimeException exception) {
                log.warn("Recurring rule generation failed. recurringId={}", recurringId, exception);
            }
        }
        return advanced;
    }
}
