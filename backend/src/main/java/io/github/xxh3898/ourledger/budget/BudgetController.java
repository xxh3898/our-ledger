package io.github.xxh3898.ourledger.budget;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.time.YearMonth;

@RestController
@RequestMapping("/api/v1/budgets")
public class BudgetController {

    private final BudgetService budgetService;

    public BudgetController(BudgetService budgetService) {
        this.budgetService = budgetService;
    }

    @GetMapping
    BudgetMonthResponse findMonth(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam @DateTimeFormat(pattern = "yyyy-MM") YearMonth month
    ) {
        return budgetService.findMonth(currentHousehold, month);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    BudgetResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody BudgetCreateRequest request
    ) {
        return budgetService.create(currentHousehold, request);
    }

    @PatchMapping("/{budgetId}")
    BudgetResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long budgetId,
            @RequestBody BudgetUpdateRequest request
    ) {
        return budgetService.update(currentHousehold, budgetId, request);
    }

    @DeleteMapping("/{budgetId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long budgetId,
            @RequestParam Long version
    ) {
        budgetService.delete(currentHousehold, budgetId, version);
    }
}
