package io.github.xxh3898.ourledger.assets;

import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/assets")
public class AssetsController {

    private final AssetsService assetsService;

    public AssetsController(AssetsService assetsService) {
        this.assetsService = assetsService;
    }

    @GetMapping
    AssetsResponse find(
            @AuthenticationPrincipal CurrentHousehold currentHousehold
    ) {
        return assetsService.find(currentHousehold);
    }
}
