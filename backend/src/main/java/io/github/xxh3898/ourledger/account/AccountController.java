package io.github.xxh3898.ourledger.account;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/accounts")
public class AccountController {

    private final AccountService accountService;

    public AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping
    List<AccountResponse> findAll(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(defaultValue = "false") boolean includeArchived
    ) {
        return accountService.findAll(currentHousehold, includeArchived);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    AccountResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody AccountCreateRequest request
    ) {
        return accountService.create(currentHousehold, request);
    }

    @PatchMapping("/{accountId}")
    AccountResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long accountId,
            @RequestBody AccountUpdateRequest request
    ) {
        return accountService.update(currentHousehold, accountId, request);
    }
}
