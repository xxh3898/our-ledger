package io.github.xxh3898.ourledger.category;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class CategoryReferenceLock {

    private final CategoryRepository categoryRepository;
    private final CategoryGroupRepository categoryGroupRepository;

    public CategoryReferenceLock(
            CategoryRepository categoryRepository,
            CategoryGroupRepository categoryGroupRepository
    ) {
        this.categoryRepository = categoryRepository;
        this.categoryGroupRepository = categoryGroupRepository;
    }

    public Category lockCategoryAndGroup(Long householdId, Long categoryId) {
        Category category = lockCategory(householdId, categoryId);
        if (category.getGroupId() != null) {
            lockGroup(householdId, category.getGroupId());
        }
        return category;
    }

    public Category lockCategory(Long householdId, Long categoryId) {
        return categoryRepository.findByIdAndHouseholdIdForUpdate(categoryId, householdId)
                .orElseThrow(this::notFound);
    }

    public CategoryGroup lockGroup(Long householdId, Long groupId) {
        return categoryGroupRepository.findByIdAndHouseholdIdForUpdate(groupId, householdId)
                .orElseThrow(this::notFound);
    }

    private ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, ApiErrorCode.RESOURCE_NOT_FOUND);
    }
}
