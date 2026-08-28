package io.github.xxh3898.ourledger.calendar;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.YearMonth;

@RestController
@RequestMapping("/api/v1/calendar")
public class CalendarController {

    private final CalendarService calendarService;

    public CalendarController(CalendarService calendarService) {
        this.calendarService = calendarService;
    }

    @GetMapping("/month")
    CalendarMonthResponse findMonth(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam @DateTimeFormat(pattern = "yyyy-MM") YearMonth month,
            @RequestParam(required = false) TransactionScope scope,
            @RequestParam(required = false) Long ownerMemberId
    ) {
        return calendarService.findMonth(currentHousehold, month, scope, ownerMemberId);
    }
}
