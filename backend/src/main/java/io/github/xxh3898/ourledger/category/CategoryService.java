package io.github.xxh3898.ourledger.category;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.recurring.RecurringReferenceGuard;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class CategoryService {

    private final CategoryRepository categoryRepository;
    private final CategoryGroupService categoryGroupService;
    private final RecurringReferenceGuard recurringReferenceGuard;

    public CategoryService(
            CategoryRepository categoryRepository,
            CategoryGroupService categoryGroupService,
            RecurringReferenceGuard recurringReferenceGuard
    ) {
        this.categoryRepository = categoryRepository;
        this.categoryGroupService = categoryGroupService;
        this.recurringReferenceGuard = recurringReferenceGuard;
    }

    @Transactional(readOnly = true)
    public List<CategoryResponse> findAll(
            CurrentHousehold currentHousehold,
            boolean includeArchived
    ) {
        List<Category> categories = includeArchived
                ? categoryRepository.findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(
                        currentHousehold.householdId())
                : categoryRepository.findAllByHouseholdIdAndArchivedAtIsNullOrderByTypeAscSortOrderAscIdAsc(
                        currentHousehold.householdId());
        return categories.stream()
                .map(this::toResponse)
                .filter(response -> includeArchived
                        || response.group() == null
                        || !response.group().archived())
                .toList();
    }

    @Transactional
    public CategoryResponse create(
            CurrentHousehold currentHousehold,
            CategoryCreateRequest request
    ) {
        validateCreate(request);
        CategoryGroup group = requireMatchingGroup(
                currentHousehold.householdId(), request.groupId(), request.type(), false);
        rejectDuplicate(
                currentHousehold.householdId(), request.type(), request.name().strip(), null);
        Category category = categoryRepository.saveAndFlush(Category.create(
                currentHousehold.householdId(),
                group == null ? null : group.getId(),
                request.name(),
                request.type(),
                request.iconKey(),
                request.colorKey(),
                request.sortOrder()
        ));
        return toResponse(category);
    }

    @Transactional
    public CategoryResponse update(
            CurrentHousehold currentHousehold,
            Long categoryId,
            CategoryUpdateRequest request
    ) {
        validateUpdate(request);
        Category category = requireCategory(currentHousehold.householdId(), categoryId);
        if (request.archived() && !category.isArchived()) {
            recurringReferenceGuard.rejectCategoryArchive(
                    category.getHouseholdId(), category.getId());
        }
        CategoryGroup group = requireMatchingGroup(
                currentHousehold.householdId(),
                request.groupId(),
                category.getType(),
                request.archived()
        );
        if (!request.archived()) {
            rejectDuplicate(
                    currentHousehold.householdId(),
                    category.getType(),
                    request.name().strip(),
                    category.getId()
            );
        }
        category.update(
                group == null ? null : group.getId(),
                request.name(),
                request.iconKey(),
                request.colorKey(),
                request.sortOrder(),
                request.archived()
        );
        categoryRepository.flush();
        return toResponse(category);
    }

    @Transactional(readOnly = true)
    public Category requireCategory(Long householdId, Long categoryId) {
        return categoryRepository.findByIdAndHouseholdId(categoryId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    @Transactional(readOnly = true)
    public boolean isEffectivelyArchived(Category category) {
        if (category.isArchived()) {
            return true;
        }
        if (category.getGroupId() == null) {
            return false;
        }
        return categoryGroupService.requireGroup(
                category.getHouseholdId(), category.getGroupId()).isArchived();
    }

    private void validateCreate(CategoryCreateRequest request) {
        RequestValidator validator = baseValidator(
                request.name(), request.iconKey(), request.colorKey(), request.sortOrder())
                .required(request.type(), "type");
        validator.throwIfInvalid();
    }

    private void validateUpdate(CategoryUpdateRequest request) {
        RequestValidator validator = baseValidator(
                request.name(), request.iconKey(), request.colorKey(), request.sortOrder())
                .required(request.archived(), "archived");
        validator.throwIfInvalid();
    }

    private RequestValidator baseValidator(
            String name,
            String iconKey,
            String colorKey,
            Integer sortOrder
    ) {
        RequestValidator validator = new RequestValidator()
                .requiredText(name, "name")
                .required(sortOrder, "sortOrder");
        if (name != null) {
            validator.check(name.strip().length() <= 100, "name", "size", "100자 이하여야 합니다.");
        }
        validateOptionalKey(validator, iconKey, "iconKey");
        validateOptionalKey(validator, colorKey, "colorKey");
        if (sortOrder != null) {
            validator.check(sortOrder >= 0, "sortOrder", "minimum", "0 이상이어야 합니다.");
        }
        return validator;
    }

    private void validateOptionalKey(RequestValidator validator, String value, String field) {
        if (value != null) {
            validator.check(!value.isBlank() && value.strip().length() <= 64,
                    field, "size", "빈 문자열이 아닌 64자 이하여야 합니다.");
        }
    }

    private CategoryGroup requireMatchingGroup(
            Long householdId,
            Long groupId,
            CategoryType type,
            boolean allowArchived
    ) {
        if (groupId == null) {
            return null;
        }
        CategoryGroup group = categoryGroupService.requireGroup(householdId, groupId);
        if (group.getType() != type) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.CATEGORY_GROUP_TYPE_MISMATCH
            );
        }
        if (group.isArchived() && !allowArchived) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.ARCHIVED_CATEGORY_GROUP_NOT_ALLOWED
            );
        }
        return group;
    }

    private void rejectDuplicate(
            Long householdId,
            CategoryType type,
            String name,
            Long excludedId
    ) {
        if (categoryRepository.existsActiveName(householdId, type.name(), name, excludedId)) {
            throw new ApiException(HttpStatus.CONFLICT, ApiErrorCode.CATEGORY_NAME_CONFLICT);
        }
    }

    private CategoryResponse toResponse(Category category) {
        CategoryResponse.Group groupResponse = null;
        if (category.getGroupId() != null) {
            CategoryGroup group = categoryGroupService.requireGroup(
                    category.getHouseholdId(), category.getGroupId());
            groupResponse = new CategoryResponse.Group(
                    group.getId(), group.getName(), group.getType(), group.isArchived());
        }
        return new CategoryResponse(
                category.getId(),
                groupResponse,
                category.getName(),
                category.getType(),
                category.getIconKey(),
                category.getColorKey(),
                category.getSortOrder(),
                category.isArchived(),
                category.getCreatedAt(),
                category.getUpdatedAt()
        );
    }
}
