package io.github.xxh3898.ourledger.statistics;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.List;

@RestController
@RequestMapping("/api/v1/statistics")
public class StatisticsController {

    private final StatisticsService statisticsService;

    public StatisticsController(StatisticsService statisticsService) {
        this.statisticsService = statisticsService;
    }

    @GetMapping
    StatisticsResponse find(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(required = false) LocalDate from,
            @RequestParam(required = false) LocalDate to,
            @RequestParam(required = false) LocalDate compareFrom,
            @RequestParam(required = false) LocalDate compareTo,
            @RequestParam(required = false) TransactionScope scope,
            @RequestParam(required = false) Long ownerMemberId
    ) {
        return statisticsService.find(currentHousehold, new StatisticsFilter(
                from,
                to,
                compareFrom,
                compareTo,
                scope,
                ownerMemberId
        ));
    }

    @GetMapping("/savings-activities")
    List<SavingsActivityResponse> findSavingsActivities(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(required = false) LocalDate from,
            @RequestParam(required = false) LocalDate to
    ) {
        return statisticsService.findSavingsActivities(currentHousehold, from, to);
    }
}
