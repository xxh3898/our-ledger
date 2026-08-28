package io.github.xxh3898.ourledger.recurring;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;

import static org.assertj.core.api.Assertions.assertThat;

class RecurrenceScheduleTest {

    @Test
    void should_advanceByIntervalDays_when_frequencyIsDaily() {
        assertThat(RecurrenceSchedule.nextAfter(
                LocalDate.of(2026, 8, 1), RecurrenceFrequency.DAILY, 3,
                LocalDate.of(2026, 8, 4), null
        )).isEqualTo(LocalDate.of(2026, 8, 7));
    }

    @Test
    void should_preserveAnchorWeekday_when_frequencyIsWeekly() {
        assertThat(RecurrenceSchedule.nextAfter(
                LocalDate.of(2026, 8, 3), RecurrenceFrequency.WEEKLY, 2,
                LocalDate.of(2026, 8, 17), null
        )).isEqualTo(LocalDate.of(2026, 8, 31));
    }

    @Test
    void should_restoreOriginalDay_when_monthlyAnchorWasClamped() {
        LocalDate start = LocalDate.of(2026, 1, 31);
        LocalDate february = RecurrenceSchedule.nextAfter(
                start, RecurrenceFrequency.MONTHLY, 1, start, null);
        LocalDate march = RecurrenceSchedule.nextAfter(
                start, RecurrenceFrequency.MONTHLY, 1, february, null);

        assertThat(february).isEqualTo(LocalDate.of(2026, 2, 28));
        assertThat(march).isEqualTo(LocalDate.of(2026, 3, 31));
    }

    @Test
    void should_restoreLeapDay_when_yearlyAnchorReachesNextLeapYear() {
        LocalDate start = LocalDate.of(2024, 2, 29);
        LocalDate year2025 = RecurrenceSchedule.nextAfter(
                start, RecurrenceFrequency.YEARLY, 1, start, null);
        LocalDate year2028 = RecurrenceSchedule.nextAfter(
                start, RecurrenceFrequency.YEARLY, 1,
                LocalDate.of(2027, 2, 28), null);

        assertThat(year2025).isEqualTo(LocalDate.of(2025, 2, 28));
        assertThat(year2028).isEqualTo(LocalDate.of(2028, 2, 29));
    }

    @Test
    void should_returnNull_when_nextOccurrenceExceedsEndDate() {
        assertThat(RecurrenceSchedule.nextAfter(
                LocalDate.of(2026, 8, 1), RecurrenceFrequency.MONTHLY, 1,
                LocalDate.of(2026, 8, 1), LocalDate.of(2026, 8, 31)
        )).isNull();
    }

    @Test
    void should_skipElapsedLocalTime_when_resumingSchedule() {
        ZoneId seoul = ZoneId.of("Asia/Seoul");
        Instant noon = LocalDate.of(2026, 8, 28)
                .atTime(12, 0).atZone(seoul).toInstant();

        assertThat(RecurrenceSchedule.firstAfterInstant(
                LocalDate.of(2026, 8, 28), RecurrenceFrequency.DAILY, 1, null,
                LocalTime.of(9, 0), seoul, noon
        )).isEqualTo(LocalDate.of(2026, 8, 29));
        assertThat(RecurrenceSchedule.firstAfterInstant(
                LocalDate.of(2026, 8, 28), RecurrenceFrequency.DAILY, 1, null,
                LocalTime.of(18, 0), seoul, noon
        )).isEqualTo(LocalDate.of(2026, 8, 28));
    }
}
