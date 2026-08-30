package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/recurring-transactions")
public class RecurringTransactionController {

    private final RecurringTransactionService recurringTransactionService;

    public RecurringTransactionController(RecurringTransactionService recurringTransactionService) {
        this.recurringTransactionService = recurringTransactionService;
    }

    @GetMapping
    List<RecurringTransactionResponse> findAll(
            @AuthenticationPrincipal CurrentHousehold currentHousehold
    ) {
        return recurringTransactionService.findAll(currentHousehold);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    RecurringTransactionResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody RecurringCreateRequest request
    ) {
        return recurringTransactionService.create(currentHousehold, request);
    }

    @PatchMapping("/{recurringTransactionId}")
    RecurringTransactionResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long recurringTransactionId,
            @RequestBody RecurringUpdateRequest request
    ) {
        return recurringTransactionService.update(
                currentHousehold, recurringTransactionId, request);
    }
}
