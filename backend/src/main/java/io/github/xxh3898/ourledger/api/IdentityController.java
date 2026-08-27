package io.github.xxh3898.ourledger.api;

import io.github.xxh3898.ourledger.household.HouseholdQueryService;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final HouseholdQueryService householdQueryService;

    public IdentityController(HouseholdQueryService householdQueryService) {
        this.householdQueryService = householdQueryService;
    }

    @GetMapping("/api/v1/me")
    MeResponse me(@AuthenticationPrincipal CurrentHousehold currentHousehold) {
        return MeResponse.from(currentHousehold);
    }

    @GetMapping("/api/v1/households/current")
    CurrentHouseholdResponse currentHousehold(
            @AuthenticationPrincipal CurrentHousehold currentHousehold
    ) {
        return CurrentHouseholdResponse.from(
                currentHousehold,
                householdQueryService.findMembers(currentHousehold.householdId())
        );
    }
}
