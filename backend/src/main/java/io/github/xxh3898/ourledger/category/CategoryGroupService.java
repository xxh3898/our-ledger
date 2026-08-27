package io.github.xxh3898.ourledger.category;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
public class CategoryGroupService {

    private final CategoryGroupRepository categoryGroupRepository;

    public CategoryGroupService(CategoryGroupRepository categoryGroupRepository) {
        this.categoryGroupRepository = categoryGroupRepository;
    }

    @Transactional(readOnly = true)
    public List<CategoryGroupResponse> findAll(
            CurrentHousehold currentHousehold,
            boolean includeArchived
    ) {
        List<CategoryGroup> groups = includeArchived
                ? categoryGroupRepository.findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(
                        currentHousehold.householdId())
                : categoryGroupRepository
                        .findAllByHouseholdIdAndArchivedAtIsNullOrderByTypeAscSortOrderAscIdAsc(
                                currentHousehold.householdId());
        return groups.stream().map(this::toResponse).toList();
    }

    @Transactional
    public CategoryGroupResponse create(
            CurrentHousehold currentHousehold,
            CategoryGroupCreateRequest request
    ) {
        validate(request.name(), request.type(), request.sortOrder());
        CategoryGroup group = categoryGroupRepository.saveAndFlush(CategoryGroup.create(
                currentHousehold.householdId(),
                request.name(),
                request.type(),
                request.sortOrder()
        ));
        return toResponse(group);
    }

    @Transactional
    public CategoryGroupResponse update(
            CurrentHousehold currentHousehold,
            Long groupId,
            CategoryGroupUpdateRequest request
    ) {
        validateUpdate(request.name(), request.sortOrder(), request.archived());
        CategoryGroup group = requireGroup(currentHousehold.householdId(), groupId);
        group.update(request.name(), request.sortOrder(), request.archived());
        categoryGroupRepository.flush();
        return toResponse(group);
    }

    @Transactional(readOnly = true)
    public CategoryGroup requireGroup(Long householdId, Long groupId) {
        return categoryGroupRepository.findByIdAndHouseholdId(groupId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private void validate(String name, CategoryType type, Integer sortOrder) {
        RequestValidator validator = baseValidator(name, sortOrder).required(type, "type");
        validator.throwIfInvalid();
    }

    private void validateUpdate(String name, Integer sortOrder, Boolean archived) {
        RequestValidator validator = baseValidator(name, sortOrder).required(archived, "archived");
        validator.throwIfInvalid();
    }

    private RequestValidator baseValidator(String name, Integer sortOrder) {
        RequestValidator validator = new RequestValidator()
                .requiredText(name, "name")
                .required(sortOrder, "sortOrder");
        if (name != null) {
            validator.check(name.strip().length() <= 100, "name", "size", "100자 이하여야 합니다.");
        }
        if (sortOrder != null) {
            validator.check(sortOrder >= 0, "sortOrder", "minimum", "0 이상이어야 합니다.");
        }
        return validator;
    }

    private CategoryGroupResponse toResponse(CategoryGroup group) {
        return new CategoryGroupResponse(
                group.getId(),
                group.getName(),
                group.getType(),
                group.getSortOrder(),
                group.isArchived(),
                group.getCreatedAt(),
                group.getUpdatedAt()
        );
    }
}
