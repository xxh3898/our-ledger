package io.github.xxh3898.ourledger.goal;

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
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/goals/marriage")
public class MarriageGoalController {

    private final MarriageGoalService marriageGoalService;

    public MarriageGoalController(MarriageGoalService marriageGoalService) {
        this.marriageGoalService = marriageGoalService;
    }

    @GetMapping
    MarriageGoalViewResponse find(
            @AuthenticationPrincipal CurrentHousehold currentHousehold
    ) {
        return marriageGoalService.find(currentHousehold);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    MarriageGoalViewResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody MarriageGoalCreateRequest request
    ) {
        return marriageGoalService.create(currentHousehold, request);
    }

    @PatchMapping
    MarriageGoalViewResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody MarriageGoalUpdateRequest request
    ) {
        return marriageGoalService.update(currentHousehold, request);
    }

    @PostMapping("/accounts/{accountId}")
    @ResponseStatus(HttpStatus.CREATED)
    MarriageGoalViewResponse linkAccount(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long accountId
    ) {
        return marriageGoalService.linkAccount(currentHousehold, accountId);
    }

    @DeleteMapping("/accounts/{accountId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void unlinkAccount(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long accountId
    ) {
        marriageGoalService.unlinkAccount(currentHousehold, accountId);
    }
}
