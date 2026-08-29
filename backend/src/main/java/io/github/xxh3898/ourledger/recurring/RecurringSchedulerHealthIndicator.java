package io.github.xxh3898.ourledger.recurring;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.boot.health.contributor.Status;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class RecurringSchedulerHealthIndicator implements HealthIndicator {

    private final RecurringSchedulerOperationalState operationalState;

    public RecurringSchedulerHealthIndicator(
            RecurringSchedulerOperationalState operationalState
    ) {
        this.operationalState = operationalState;
    }

    @Override
    public Health health() {
        RecurringSchedulerOperationalState.HealthView view = operationalState.healthView();
        RecurringSchedulerOperationalState.Snapshot snapshot = view.snapshot();
        Status status = statusFor(view);
        Map<String, Object> details = new LinkedHashMap<>();
        details.put("enabled", snapshot.enabled());
        details.put("processStartedAt", instant(snapshot.processStartedAt()));
        details.put("pollCountSinceStart", snapshot.pollCountSinceStart());
        details.put("lastPollStartedAt", instant(snapshot.lastPollStartedAt()));
        details.put("lastPollCompletedAt", instant(snapshot.lastPollCompletedAt()));
        details.put("lastPollSucceeded", snapshot.lastPollSucceeded());
        details.put("lastAdvancedOccurrenceCount", snapshot.lastAdvancedOccurrenceCount());
        details.put("lastPollRuleFailureCount", snapshot.lastPollRuleFailureCount());
        details.put("totalRuleFailureCountSinceStart", snapshot.totalRuleFailureCountSinceStart());
        details.put(
                "consecutivePollExecutionFailures",
                snapshot.consecutivePollExecutionFailures()
        );
        details.put(
                "lastPollExecutionFailureAt",
                instant(snapshot.lastPollExecutionFailureAt())
        );
        details.put("lastRuleFailureAt", instant(snapshot.lastRuleFailureAt()));
        return Health.status(status).withDetails(details).build();
    }

    private Status statusFor(RecurringSchedulerOperationalState.HealthView view) {
        RecurringSchedulerOperationalState.Snapshot snapshot = view.snapshot();
        if (view.pollInProgress() || snapshot.pollCountSinceStart() == 0) {
            return Status.UNKNOWN;
        }
        return Boolean.TRUE.equals(snapshot.lastPollSucceeded()) ? Status.UP : Status.DOWN;
    }

    private String instant(Instant instant) {
        return instant == null ? null : instant.toString();
    }
}
