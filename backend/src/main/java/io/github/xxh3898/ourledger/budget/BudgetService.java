package io.github.xxh3898.ourledger.budget;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.household.HouseholdMemberSummary;
import io.github.xxh3898.ourledger.household.HouseholdQueryService;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.NetSpendingCalculator;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@Service
public class BudgetService {

    private static final String IDENTITY_CONSTRAINT = "uq_budgets_identity";

    private final BudgetRepository budgetRepository;
    private final LedgerTransactionRepository transactionRepository;
    private final HouseholdMemberResolver householdMemberResolver;
    private final HouseholdQueryService householdQueryService;
    private final CategoryService categoryService;

    public BudgetService(
            BudgetRepository budgetRepository,
            LedgerTransactionRepository transactionRepository,
            HouseholdMemberResolver householdMemberResolver,
            HouseholdQueryService householdQueryService,
            CategoryService categoryService
    ) {
        this.budgetRepository = budgetRepository;
        this.transactionRepository = transactionRepository;
        this.householdMemberResolver = householdMemberResolver;
        this.householdQueryService = householdQueryService;
        this.categoryService = categoryService;
    }

    @Transactional(readOnly = true)
    public BudgetMonthResponse findMonth(CurrentHousehold currentHousehold, YearMonth month) {
        new RequestValidator().required(month, "month").throwIfInvalid();
        LocalDate budgetMonth = month.atDay(1);
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        List<Budget> budgets = budgetRepository
                .findAllByHouseholdIdAndBudgetMonthOrderByIdAsc(
                        currentHousehold.householdId(), budgetMonth);
        List<LedgerTransaction> transactions = transactionRepository
                .findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                        currentHousehold.householdId(),
                        budgetMonth.atStartOfDay(zoneId).toInstant(),
                        month.plusMonths(1).atDay(1).atStartOfDay(zoneId).toInstant()
                );
        List<HouseholdMemberSummary> members = householdQueryService
                .findMembers(currentHousehold.householdId());

        List<BudgetMonthResponse.ScopeBudget> scopes = new ArrayList<>();
        scopes.add(toScopeBudget(
                findBudget(budgets, BudgetScope.HOUSEHOLD, null, null),
                BudgetScope.HOUSEHOLD,
                null,
                transactions
        ));
        for (HouseholdMemberSummary member : members) {
            BudgetResponse.Member owner = toMember(member);
            scopes.add(toScopeBudget(
                    findBudget(budgets, BudgetScope.PERSONAL, member.memberId(), null),
                    BudgetScope.PERSONAL,
                    owner,
                    transactions
            ));
        }
        scopes.add(toScopeBudget(
                findBudget(budgets, BudgetScope.SHARED, null, null),
                BudgetScope.SHARED,
                null,
                transactions
        ));

        List<BudgetMonthResponse.CategoryBudget> categoryBudgets = budgets.stream()
                .filter(budget -> budget.getCategoryId() != null)
                .map(budget -> toCategoryBudget(budget, transactions))
                .sorted(Comparator
                        .comparingInt((BudgetMonthResponse.CategoryBudget item) ->
                                scopeOrder(item.scope()))
                        .thenComparing(item -> item.owner() == null
                                ? "" : item.owner().displayName())
                        .thenComparing(item -> item.category().name())
                        .thenComparing(BudgetMonthResponse.CategoryBudget::budgetId))
                .toList();

        return new BudgetMonthResponse(month, zoneId.getId(), scopes, categoryBudgets);
    }

    @Transactional
    public BudgetResponse create(
            CurrentHousehold currentHousehold,
            BudgetCreateRequest request
    ) {
        ValidatedIdentity identity = validateIdentity(
                currentHousehold,
                request.month(),
                request.scope(),
                request.ownerMemberId(),
                request.categoryId(),
                request.amount()
        );
        rejectDuplicate(currentHousehold.householdId(), identity, null);
        Budget budget = Budget.create(
                currentHousehold.householdId(),
                identity.budgetMonth(),
                identity.scope(),
                identity.ownerMemberId(),
                identity.categoryId(),
                identity.amount()
        );
        try {
            return toResponse(budgetRepository.saveAndFlush(budget));
        } catch (DataIntegrityViolationException exception) {
            throw mapDataConflict(exception);
        }
    }

    @Transactional
    public BudgetResponse update(
            CurrentHousehold currentHousehold,
            Long budgetId,
            BudgetUpdateRequest request
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        Budget budget = requireBudget(currentHousehold.householdId(), budgetId);
        rejectStaleVersion(budget, request.version());
        ValidatedIdentity identity = validateIdentity(
                currentHousehold,
                request.month(),
                request.scope(),
                request.ownerMemberId(),
                request.categoryId(),
                request.amount()
        );
        rejectDuplicate(currentHousehold.householdId(), identity, budget.getId());
        budget.update(
                identity.budgetMonth(),
                identity.scope(),
                identity.ownerMemberId(),
                identity.categoryId(),
                identity.amount()
        );
        try {
            budgetRepository.flush();
            return toResponse(budget);
        } catch (DataIntegrityViolationException exception) {
            throw mapDataConflict(exception);
        } catch (ObjectOptimisticLockingFailureException exception) {
            throw versionConflict();
        }
    }

    @Transactional
    public void delete(CurrentHousehold currentHousehold, Long budgetId, Long version) {
        Budget budget = requireBudget(currentHousehold.householdId(), budgetId);
        rejectStaleVersion(budget, version);
        try {
            budgetRepository.delete(budget);
            budgetRepository.flush();
        } catch (ObjectOptimisticLockingFailureException exception) {
            throw versionConflict();
        }
    }

    private ValidatedIdentity validateIdentity(
            CurrentHousehold currentHousehold,
            YearMonth month,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            Long amount
    ) {
        RequestValidator validator = new RequestValidator()
                .required(month, "month")
                .required(scope, "scope")
                .required(amount, "amount");
        if (amount != null) {
            validator.check(amount >= 0, "amount", "minimum", "0 이상이어야 합니다.");
        }
        if (scope == BudgetScope.PERSONAL) {
            validator.required(ownerMemberId, "ownerMemberId");
        } else if (scope != null) {
            validator.check(
                    ownerMemberId == null,
                    "ownerMemberId",
                    "mustBeNull",
                    "HOUSEHOLD/SHARED scope에는 ownerMemberId를 지정하지 않습니다."
            );
        }
        validator.throwIfInvalid();

        HouseholdMember owner = scope == BudgetScope.PERSONAL
                ? householdMemberResolver.require(currentHousehold.householdId(), ownerMemberId)
                : null;
        Category category = categoryId == null
                ? null
                : categoryService.requireCategory(currentHousehold.householdId(), categoryId);
        if (category != null && category.getType() != CategoryType.EXPENSE) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.CATEGORY_TYPE_MISMATCH
            );
        }
        if (category != null && categoryService.isEffectivelyArchived(category)) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.ARCHIVED_CATEGORY_NOT_ALLOWED
            );
        }
        return new ValidatedIdentity(
                month.atDay(1),
                scope,
                owner == null ? null : owner.getId(),
                category == null ? null : category.getId(),
                amount
        );
    }

    private void rejectDuplicate(Long householdId, ValidatedIdentity identity, Long excludedId) {
        if (budgetRepository.existsIdentity(
                householdId,
                identity.budgetMonth(),
                identity.scope().name(),
                identity.ownerMemberId(),
                identity.categoryId(),
                excludedId
        )) {
            throw duplicate();
        }
    }

    private Budget requireBudget(Long householdId, Long budgetId) {
        return budgetRepository.findByIdAndHouseholdId(budgetId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private void rejectStaleVersion(Budget budget, Long requestedVersion) {
        if (requestedVersion == null || budget.getVersion() != requestedVersion) {
            throw versionConflict();
        }
    }

    private RuntimeException mapDataConflict(DataIntegrityViolationException exception) {
        Throwable current = exception;
        while (current != null) {
            String message = current.getMessage();
            if (message != null && message.contains(IDENTITY_CONSTRAINT)) {
                return duplicate();
            }
            current = current.getCause();
        }
        return exception;
    }

    private ApiException duplicate() {
        return new ApiException(HttpStatus.CONFLICT, ApiErrorCode.BUDGET_DUPLICATE);
    }

    private ApiException versionConflict() {
        return new ApiException(HttpStatus.CONFLICT, ApiErrorCode.BUDGET_VERSION_CONFLICT);
    }

    private Budget findBudget(
            List<Budget> budgets,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId
    ) {
        return budgets.stream()
                .filter(budget -> budget.getScope() == scope)
                .filter(budget -> Objects.equals(budget.getOwnerMemberId(), ownerMemberId))
                .filter(budget -> Objects.equals(budget.getCategoryId(), categoryId))
                .findFirst()
                .orElse(null);
    }

    private BudgetMonthResponse.ScopeBudget toScopeBudget(
            Budget budget,
            BudgetScope scope,
            BudgetResponse.Member owner,
            List<LedgerTransaction> transactions
    ) {
        long spentAmount = spentAmount(
                transactions,
                scope,
                owner == null ? null : owner.memberId(),
                null
        );
        if (budget == null) {
            return new BudgetMonthResponse.ScopeBudget(
                    scope,
                    owner,
                    null,
                    null,
                    null,
                    spentAmount,
                    null,
                    false
            );
        }
        long remainingAmount = Math.subtractExact(budget.getAmount(), spentAmount);
        return new BudgetMonthResponse.ScopeBudget(
                scope,
                owner,
                budget.getId(),
                budget.getVersion(),
                budget.getAmount(),
                spentAmount,
                remainingAmount,
                spentAmount > budget.getAmount()
        );
    }

    private BudgetMonthResponse.CategoryBudget toCategoryBudget(
            Budget budget,
            List<LedgerTransaction> transactions
    ) {
        BudgetResponse.Member owner = budget.getOwnerMemberId() == null
                ? null
                : toMember(householdMemberResolver.require(
                        budget.getHouseholdId(), budget.getOwnerMemberId()));
        Category category = categoryService.requireCategory(
                budget.getHouseholdId(), budget.getCategoryId());
        long spentAmount = spentAmount(
                transactions,
                budget.getScope(),
                budget.getOwnerMemberId(),
                budget.getCategoryId()
        );
        long remainingAmount = Math.subtractExact(budget.getAmount(), spentAmount);
        return new BudgetMonthResponse.CategoryBudget(
                budget.getId(),
                budget.getVersion(),
                budget.getScope(),
                owner,
                toCategory(category),
                budget.getAmount(),
                spentAmount,
                remainingAmount,
                spentAmount > budget.getAmount()
        );
    }

    private long spentAmount(
            List<LedgerTransaction> transactions,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId
    ) {
        long spent = 0;
        for (LedgerTransaction transaction : transactions) {
            if (transaction.getType() != TransactionType.EXPENSE
                    || !matchesScope(transaction, scope, ownerMemberId)
                    || (categoryId != null
                    && !Objects.equals(transaction.getCategoryId(), categoryId))) {
                continue;
            }
            spent = Math.addExact(spent, NetSpendingCalculator.amountOf(transaction));
        }
        return spent;
    }

    private boolean matchesScope(
            LedgerTransaction transaction,
            BudgetScope scope,
            Long ownerMemberId
    ) {
        if (scope == BudgetScope.HOUSEHOLD) {
            return true;
        }
        if (scope == BudgetScope.SHARED) {
            return transaction.getScope() == TransactionScope.SHARED;
        }
        return transaction.getScope() == TransactionScope.PERSONAL
                && Objects.equals(transaction.getOwnerMemberId(), ownerMemberId);
    }

    private BudgetResponse toResponse(Budget budget) {
        HouseholdMember owner = budget.getOwnerMemberId() == null
                ? null
                : householdMemberResolver.require(
                        budget.getHouseholdId(), budget.getOwnerMemberId());
        Category category = budget.getCategoryId() == null
                ? null
                : categoryService.requireCategory(
                        budget.getHouseholdId(), budget.getCategoryId());
        return new BudgetResponse(
                budget.getId(),
                YearMonth.from(budget.getBudgetMonth()),
                budget.getScope(),
                toMember(owner),
                toCategory(category),
                budget.getAmount(),
                budget.getVersion(),
                budget.getCreatedAt(),
                budget.getUpdatedAt()
        );
    }

    private BudgetResponse.Member toMember(HouseholdMember member) {
        if (member == null) {
            return null;
        }
        return new BudgetResponse.Member(
                member.getId(),
                member.getUser().getId(),
                member.getUser().getDisplayName()
        );
    }

    private BudgetResponse.Member toMember(HouseholdMemberSummary member) {
        return new BudgetResponse.Member(
                member.memberId(),
                member.userId(),
                member.displayName()
        );
    }

    private BudgetResponse.CategoryReference toCategory(Category category) {
        if (category == null) {
            return null;
        }
        return new BudgetResponse.CategoryReference(
                category.getId(),
                category.getName(),
                category.getType(),
                categoryService.isEffectivelyArchived(category)
        );
    }

    private int scopeOrder(BudgetScope scope) {
        return switch (scope) {
            case HOUSEHOLD -> 0;
            case PERSONAL -> 1;
            case SHARED -> 2;
        };
    }

    private record ValidatedIdentity(
            LocalDate budgetMonth,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
    }
}
