package io.github.xxh3898.ourledger.transaction;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
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

import java.time.LocalDate;
import java.util.List;

@RestController
@RequestMapping("/api/v1/transactions")
public class TransactionController {

    private final TransactionService transactionService;

    public TransactionController(TransactionService transactionService) {
        this.transactionService = transactionService;
    }

    @GetMapping
    List<TransactionResponse> findAll(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(required = false) LocalDate from,
            @RequestParam(required = false) LocalDate to,
            @RequestParam(required = false) TransactionType type,
            @RequestParam(required = false) TransactionScope scope,
            @RequestParam(required = false) Long ownerMemberId,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) Long accountId
    ) {
        return transactionService.findAll(
                currentHousehold,
                new TransactionFilter(
                        from,
                        to,
                        type,
                        scope,
                        ownerMemberId,
                        categoryId,
                        accountId
                )
        );
    }

    @GetMapping("/{transactionId}")
    TransactionResponse findOne(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long transactionId
    ) {
        return transactionService.findOne(currentHousehold, transactionId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    TransactionResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody TransactionCreateRequest request
    ) {
        return transactionService.create(currentHousehold, request);
    }

    @PatchMapping("/{transactionId}")
    TransactionResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long transactionId,
            @RequestBody TransactionUpdateRequest request
    ) {
        return transactionService.update(currentHousehold, transactionId, request);
    }

    @DeleteMapping("/{transactionId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long transactionId,
            @RequestParam Long version
    ) {
        transactionService.delete(currentHousehold, transactionId, version);
    }
}
