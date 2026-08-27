package io.github.xxh3898.ourledger.category;

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
@RequestMapping("/api/v1/category-groups")
public class CategoryGroupController {

    private final CategoryGroupService categoryGroupService;

    public CategoryGroupController(CategoryGroupService categoryGroupService) {
        this.categoryGroupService = categoryGroupService;
    }

    @GetMapping
    List<CategoryGroupResponse> findAll(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(defaultValue = "false") boolean includeArchived
    ) {
        return categoryGroupService.findAll(currentHousehold, includeArchived);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    CategoryGroupResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody CategoryGroupCreateRequest request
    ) {
        return categoryGroupService.create(currentHousehold, request);
    }

    @PatchMapping("/{groupId}")
    CategoryGroupResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long groupId,
            @RequestBody CategoryGroupUpdateRequest request
    ) {
        return categoryGroupService.update(currentHousehold, groupId, request);
    }
}
