package io.github.xxh3898.ourledger.calendar;

import java.time.LocalDate;
import java.time.YearMonth;
import java.util.List;

public record CalendarMonthResponse(
        YearMonth month,
        String timezone,
        Summary summary,
        List<Day> days
) {

    public CalendarMonthResponse {
        days = List.copyOf(days);
    }

    public record Summary(
            long netSpendingAmount,
            long previousMonthNetSpendingAmount,
            long differenceAmount
    ) {
    }

    public record Day(
            LocalDate date,
            long transactionCount,
            long netSpendingAmount
    ) {
    }
}
