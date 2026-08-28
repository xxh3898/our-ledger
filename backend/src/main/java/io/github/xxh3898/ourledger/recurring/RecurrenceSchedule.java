package io.github.xxh3898.ourledger.recurring;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.YearMonth;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;

public final class RecurrenceSchedule {

    private RecurrenceSchedule() {
    }

    public static LocalDate nextAfter(
            LocalDate startDate,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate afterExclusive,
            LocalDate endDate
    ) {
        requireValid(startDate, frequency, intervalValue);
        LocalDate candidate = switch (frequency) {
            case DAILY -> nextDaily(startDate, intervalValue, afterExclusive);
            case WEEKLY -> nextDaily(
                    startDate,
                    Math.multiplyExact(intervalValue, 7),
                    afterExclusive
            );
            case MONTHLY -> nextMonthly(startDate, intervalValue, afterExclusive);
            case YEARLY -> nextYearly(startDate, intervalValue, afterExclusive);
        };
        return endDate != null && candidate.isAfter(endDate) ? null : candidate;
    }

    public static LocalDate firstOnOrAfter(
            LocalDate startDate,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate minimumDate,
            LocalDate endDate
    ) {
        if (!startDate.isBefore(minimumDate)) {
            return endDate != null && startDate.isAfter(endDate) ? null : startDate;
        }
        return nextAfter(startDate, frequency, intervalValue, minimumDate.minusDays(1), endDate);
    }

    public static LocalDate firstAfterInstant(
            LocalDate startDate,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate endDate,
            LocalTime scheduledLocalTime,
            ZoneId zoneId,
            Instant afterExclusive
    ) {
        LocalDate localDate = afterExclusive.atZone(zoneId).toLocalDate();
        LocalDate candidate = firstOnOrAfter(
                startDate, frequency, intervalValue, localDate, endDate);
        if (candidate == null) {
            return null;
        }
        Instant candidateInstant = candidate.atTime(scheduledLocalTime).atZone(zoneId).toInstant();
        if (candidateInstant.isAfter(afterExclusive)) {
            return candidate;
        }
        return nextAfter(startDate, frequency, intervalValue, candidate, endDate);
    }

    private static LocalDate nextDaily(
            LocalDate startDate,
            int intervalDays,
            LocalDate afterExclusive
    ) {
        if (afterExclusive.isBefore(startDate)) {
            return startDate;
        }
        long days = ChronoUnit.DAYS.between(startDate, afterExclusive);
        long steps = Math.floorDiv(days, intervalDays) + 1;
        return startDate.plusDays(Math.multiplyExact(steps, intervalDays));
    }

    private static LocalDate nextMonthly(
            LocalDate startDate,
            int intervalMonths,
            LocalDate afterExclusive
    ) {
        if (afterExclusive.isBefore(startDate)) {
            return startDate;
        }
        YearMonth anchorMonth = YearMonth.from(startDate);
        long monthDistance = ChronoUnit.MONTHS.between(anchorMonth, YearMonth.from(afterExclusive));
        long steps = Math.max(0, Math.floorDiv(monthDistance, intervalMonths));
        LocalDate candidate = monthlyCandidate(startDate, intervalMonths, steps);
        if (!candidate.isAfter(afterExclusive)) {
            candidate = monthlyCandidate(startDate, intervalMonths, steps + 1);
        }
        return candidate;
    }

    private static LocalDate monthlyCandidate(
            LocalDate startDate,
            int intervalMonths,
            long steps
    ) {
        YearMonth month = YearMonth.from(startDate)
                .plusMonths(Math.multiplyExact(steps, intervalMonths));
        return month.atDay(Math.min(startDate.getDayOfMonth(), month.lengthOfMonth()));
    }

    private static LocalDate nextYearly(
            LocalDate startDate,
            int intervalYears,
            LocalDate afterExclusive
    ) {
        if (afterExclusive.isBefore(startDate)) {
            return startDate;
        }
        long yearDistance = afterExclusive.getYear() - (long) startDate.getYear();
        long steps = Math.max(0, Math.floorDiv(yearDistance, intervalYears));
        LocalDate candidate = yearlyCandidate(startDate, intervalYears, steps);
        if (!candidate.isAfter(afterExclusive)) {
            candidate = yearlyCandidate(startDate, intervalYears, steps + 1);
        }
        return candidate;
    }

    private static LocalDate yearlyCandidate(
            LocalDate startDate,
            int intervalYears,
            long steps
    ) {
        int year = Math.toIntExact(
                startDate.getYear() + Math.multiplyExact(steps, intervalYears));
        YearMonth month = YearMonth.of(year, startDate.getMonth());
        return month.atDay(Math.min(startDate.getDayOfMonth(), month.lengthOfMonth()));
    }

    private static void requireValid(
            LocalDate startDate,
            RecurrenceFrequency frequency,
            int intervalValue
    ) {
        if (startDate == null || frequency == null || intervalValue <= 0) {
            throw new IllegalArgumentException("유효한 반복 일정이 필요합니다.");
        }
    }
}
