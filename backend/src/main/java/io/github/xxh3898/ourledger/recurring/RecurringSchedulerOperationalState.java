package io.github.xxh3898.ourledger.recurring;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Clock;
import java.time.Instant;

@Component
public class RecurringSchedulerOperationalState {

    private final boolean enabled;
    private final Instant processStartedAt;

    private long pollCountSinceStart;
    private Instant lastPollStartedAt;
    private Instant lastPollCompletedAt;
    private Boolean lastPollSucceeded;
    private int lastAdvancedOccurrenceCount;
    private long lastPollRuleFailureCount;
    private long totalRuleFailureCountSinceStart;
    private long consecutivePollExecutionFailures;
    private Instant lastPollExecutionFailureAt;
    private Instant lastRuleFailureAt;
    private boolean pollInProgress;

    public RecurringSchedulerOperationalState(
            Clock clock,
            @Value("${our-ledger.recurring.scheduler.enabled:true}") boolean enabled
    ) {
        this.enabled = enabled;
        this.processStartedAt = clock.instant();
    }

    public synchronized void pollStarted(Instant startedAt) {
        pollCountSinceStart++;
        lastPollStartedAt = startedAt;
        lastPollRuleFailureCount = 0;
        pollInProgress = true;
    }

    public synchronized void pollSucceeded(Instant completedAt, int advancedOccurrenceCount) {
        lastPollCompletedAt = completedAt;
        lastPollSucceeded = true;
        lastAdvancedOccurrenceCount = advancedOccurrenceCount;
        consecutivePollExecutionFailures = 0;
        pollInProgress = false;
    }

    public synchronized void pollFailed(Instant failedAt) {
        lastPollCompletedAt = failedAt;
        lastPollSucceeded = false;
        lastAdvancedOccurrenceCount = 0;
        consecutivePollExecutionFailures++;
        lastPollExecutionFailureAt = failedAt;
        pollInProgress = false;
    }

    public synchronized void ruleFailed(Instant failedAt) {
        totalRuleFailureCountSinceStart++;
        lastRuleFailureAt = failedAt;
        if (pollInProgress) {
            lastPollRuleFailureCount++;
        }
    }

    public synchronized Snapshot snapshot() {
        return snapshotUnsafe();
    }

    synchronized HealthView healthView() {
        return new HealthView(snapshotUnsafe(), pollInProgress);
    }

    private Snapshot snapshotUnsafe() {
        return new Snapshot(
                enabled,
                processStartedAt,
                pollCountSinceStart,
                lastPollStartedAt,
                lastPollCompletedAt,
                lastPollSucceeded,
                lastAdvancedOccurrenceCount,
                lastPollRuleFailureCount,
                totalRuleFailureCountSinceStart,
                consecutivePollExecutionFailures,
                lastPollExecutionFailureAt,
                lastRuleFailureAt
        );
    }

    public record Snapshot(
            boolean enabled,
            Instant processStartedAt,
            long pollCountSinceStart,
            Instant lastPollStartedAt,
            Instant lastPollCompletedAt,
            Boolean lastPollSucceeded,
            int lastAdvancedOccurrenceCount,
            long lastPollRuleFailureCount,
            long totalRuleFailureCountSinceStart,
            long consecutivePollExecutionFailures,
            Instant lastPollExecutionFailureAt,
            Instant lastRuleFailureAt
    ) {
    }

    record HealthView(Snapshot snapshot, boolean pollInProgress) {
    }
}
