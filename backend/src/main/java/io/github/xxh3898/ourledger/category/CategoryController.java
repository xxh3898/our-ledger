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
@RequestMapping("/api/v1/categories")
public class CategoryController {

    private final CategoryService categoryService;

    public CategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @GetMapping
    List<CategoryResponse> findAll(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestParam(defaultValue = "false") boolean includeArchived
    ) {
        return categoryService.findAll(currentHousehold, includeArchived);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    CategoryResponse create(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @RequestBody CategoryCreateRequest request
    ) {
        return categoryService.create(currentHousehold, request);
    }

    @PatchMapping("/{categoryId}")
    CategoryResponse update(
            @AuthenticationPrincipal CurrentHousehold currentHousehold,
            @PathVariable Long categoryId,
            @RequestBody CategoryUpdateRequest request
    ) {
        return categoryService.update(currentHousehold, categoryId, request);
    }
}
