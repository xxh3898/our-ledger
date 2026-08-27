package io.github.xxh3898.ourledger.transaction;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

@Service
public class TransactionService {

    private final LedgerTransactionRepository transactionRepository;
    private final TransactionAccountEntryRepository entryRepository;
    private final HouseholdMemberResolver householdMemberResolver;
    private final CategoryService categoryService;
    private final AccountService accountService;

    public TransactionService(
            LedgerTransactionRepository transactionRepository,
            TransactionAccountEntryRepository entryRepository,
            HouseholdMemberResolver householdMemberResolver,
            CategoryService categoryService,
            AccountService accountService
    ) {
        this.transactionRepository = transactionRepository;
        this.entryRepository = entryRepository;
        this.householdMemberResolver = householdMemberResolver;
        this.categoryService = categoryService;
        this.accountService = accountService;
    }

    @Transactional(readOnly = true)
    public List<TransactionResponse> findAll(
            CurrentHousehold currentHousehold,
            TransactionFilter filter
    ) {
        validateFilter(filter);
        Specification<LedgerTransaction> specification =
                TransactionSpecifications.visibleTo(currentHousehold.householdId());
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        if (filter.from() != null) {
            specification = specification.and(TransactionSpecifications.occurredAtOrAfter(
                    filter.from().atStartOfDay(zoneId).toInstant()));
        }
        if (filter.to() != null) {
            specification = specification.and(TransactionSpecifications.occurredBefore(
                    filter.to().plusDays(1).atStartOfDay(zoneId).toInstant()));
        }
        if (filter.type() != null) {
            specification = specification.and(TransactionSpecifications.typeEquals(filter.type()));
        }
        if (filter.scope() != null) {
            specification = specification.and(TransactionSpecifications.scopeEquals(filter.scope()));
        }
        if (filter.ownerMemberId() != null) {
            specification = specification.and(
                    TransactionSpecifications.ownerEquals(filter.ownerMemberId()));
        }
        if (filter.categoryId() != null) {
            specification = specification.and(
                    TransactionSpecifications.categoryEquals(filter.categoryId()));
        }
        if (filter.accountId() != null) {
            specification = specification.and(
                    TransactionSpecifications.accountEquals(filter.accountId()));
        }
        Sort sort = Sort.by(
                Sort.Order.desc("occurredAt"),
                Sort.Order.desc("id")
        );
        return transactionRepository.findAll(specification, sort)
                .stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public TransactionResponse findOne(CurrentHousehold currentHousehold, Long transactionId) {
        return toResponse(requireTransaction(currentHousehold.householdId(), transactionId));
    }

    @Transactional
    public TransactionResponse create(
            CurrentHousehold currentHousehold,
            TransactionCreateRequest request
    ) {
        ValidatedPosting posting = validatePosting(
                currentHousehold,
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.accountId(),
                request.occurredAt(),
                request.memo(),
                request.adjustmentType(),
                request.reversesTransactionId()
        );
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        LedgerTransaction transaction = transactionRepository.saveAndFlush(LedgerTransaction.create(
                currentHousehold.householdId(),
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.occurredAt(),
                request.memo(),
                request.adjustmentType(),
                request.reversesTransactionId(),
                actor.getId()
        ));
        entryRepository.saveAndFlush(TransactionAccountEntry.primary(
                currentHousehold.householdId(),
                transaction.getId(),
                posting.account().getId(),
                posting.balanceDelta()
        ));
        return toResponse(transaction);
    }

    @Transactional
    public TransactionResponse update(
            CurrentHousehold currentHousehold,
            Long transactionId,
            TransactionUpdateRequest request
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        LedgerTransaction transaction = requireTransaction(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, request.version());
        ValidatedPosting posting = validatePosting(
                currentHousehold,
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.accountId(),
                request.occurredAt(),
                request.memo(),
                request.adjustmentType(),
                request.reversesTransactionId()
        );
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        transaction.update(
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.occurredAt(),
                request.memo(),
                request.adjustmentType(),
                request.reversesTransactionId(),
                actor.getId()
        );
        TransactionAccountEntry entry = requirePrimaryEntry(transaction);
        entry.updatePrimary(posting.account().getId(), posting.balanceDelta());
        transactionRepository.flush();
        entryRepository.flush();
        return toResponse(transaction);
    }

    @Transactional
    public void delete(
            CurrentHousehold currentHousehold,
            Long transactionId,
            Long version
    ) {
        LedgerTransaction transaction = requireTransaction(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, version);
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        transaction.delete(actor.getId());
        transactionRepository.flush();
    }

    private void validateFilter(TransactionFilter filter) {
        if (filter.from() != null && filter.to() != null && filter.from().isAfter(filter.to())) {
            RequestValidator validator = new RequestValidator();
            validator.reject("from", "range", "from은 to보다 늦을 수 없습니다.");
            validator.throwIfInvalid();
        }
    }

    private ValidatedPosting validatePosting(
            CurrentHousehold currentHousehold,
            TransactionType type,
            Long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId
    ) {
        new RequestValidator().required(type, "type").throwIfInvalid();
        if (type == TransactionType.TRANSFER) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_TRANSACTION_TYPE
            );
        }

        new RequestValidator().required(adjustmentType, "adjustmentType").throwIfInvalid();
        if (adjustmentType != AdjustmentType.NORMAL || reversesTransactionId != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_ADJUSTMENT_TYPE
            );
        }

        RequestValidator validator = new RequestValidator()
                .required(amount, "amount")
                .required(scope, "scope")
                .required(categoryId, "categoryId")
                .required(accountId, "accountId")
                .required(occurredAt, "occurredAt");
        if (amount != null) {
            validator.check(amount > 0, "amount", "positive", "1 이상이어야 합니다.");
        }
        if (memo != null) {
            validator.check(!memo.isBlank() && memo.strip().length() <= 500,
                    "memo", "size", "빈 문자열이 아닌 500자 이하여야 합니다.");
        }
        validator.throwIfInvalid();

        validateScope(scope, ownerMemberId);
        if (type != TransactionType.EXPENSE && payerMemberId != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_INVALID_SCOPE
            );
        }

        if (ownerMemberId != null) {
            householdMemberResolver.require(currentHousehold.householdId(), ownerMemberId);
        }
        if (payerMemberId != null) {
            householdMemberResolver.require(currentHousehold.householdId(), payerMemberId);
        }

        Category category = categoryService.requireCategory(
                currentHousehold.householdId(), categoryId);
        CategoryType expectedCategoryType = CategoryType.valueOf(type.name());
        if (category.getType() != expectedCategoryType) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.CATEGORY_TYPE_MISMATCH
            );
        }
        if (categoryService.isEffectivelyArchived(category)) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.ARCHIVED_CATEGORY_NOT_ALLOWED
            );
        }

        Account account = accountService.requireAccount(
                currentHousehold.householdId(), accountId);
        if (account.isArchived()) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.ARCHIVED_ACCOUNT_NOT_ALLOWED
            );
        }
        if (account.getNature() != AccountNature.ASSET
                || account.getType() == AccountType.CREDIT_CARD) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_ACCOUNT_POSTING
            );
        }
        long balanceDelta = type == TransactionType.INCOME
                ? amount
                : Math.negateExact(amount);
        return new ValidatedPosting(account, balanceDelta);
    }

    private void validateScope(TransactionScope scope, Long ownerMemberId) {
        boolean valid = (scope == TransactionScope.PERSONAL && ownerMemberId != null)
                || (scope == TransactionScope.SHARED && ownerMemberId == null);
        if (!valid) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_INVALID_SCOPE
            );
        }
    }

    private LedgerTransaction requireTransaction(Long householdId, Long transactionId) {
        return transactionRepository.findByIdAndHouseholdIdAndDeletedAtIsNull(
                        transactionId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private TransactionAccountEntry requirePrimaryEntry(LedgerTransaction transaction) {
        return entryRepository.findByTransactionIdAndHouseholdIdAndEntryRole(
                        transaction.getId(),
                        transaction.getHouseholdId(),
                        EntryRole.PRIMARY
                )
                .orElseThrow(() -> new ApiException(
                        HttpStatus.CONFLICT,
                        ApiErrorCode.RESOURCE_STATE_CONFLICT
                ));
    }

    private void rejectStaleVersion(LedgerTransaction transaction, Long requestedVersion) {
        if (requestedVersion == null || transaction.getVersion() != requestedVersion) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.TRANSACTION_VERSION_CONFLICT
            );
        }
    }

    private TransactionResponse toResponse(LedgerTransaction transaction) {
        HouseholdMember owner = transaction.getOwnerMemberId() == null
                ? null
                : householdMemberResolver.require(
                        transaction.getHouseholdId(), transaction.getOwnerMemberId());
        HouseholdMember payer = transaction.getPayerMemberId() == null
                ? null
                : householdMemberResolver.require(
                        transaction.getHouseholdId(), transaction.getPayerMemberId());
        Category category = categoryService.requireCategory(
                transaction.getHouseholdId(), transaction.getCategoryId());
        Account account = accountService.requireAccount(
                transaction.getHouseholdId(), requirePrimaryEntry(transaction).getAccountId());
        TransactionAccountEntry entry = requirePrimaryEntry(transaction);
        return new TransactionResponse(
                transaction.getId(),
                transaction.getType(),
                transaction.getAmount(),
                transaction.getScope(),
                toMember(owner),
                toMember(payer),
                new TransactionResponse.CategoryReference(
                        category.getId(),
                        category.getName(),
                        category.getType(),
                        categoryService.isEffectivelyArchived(category)
                ),
                new TransactionResponse.AccountReference(
                        account.getId(),
                        account.getName(),
                        account.getType(),
                        account.getNature(),
                        account.isArchived()
                ),
                transaction.getOccurredAt(),
                transaction.getMemo(),
                transaction.getAdjustmentType(),
                transaction.getVersion(),
                new TransactionResponse.Entry(
                        entry.getId(), entry.getEntryRole(), entry.getBalanceDelta()),
                transaction.getCreatedAt(),
                transaction.getUpdatedAt()
        );
    }

    private TransactionResponse.Member toMember(HouseholdMember member) {
        if (member == null) {
            return null;
        }
        return new TransactionResponse.Member(
                member.getId(),
                member.getUser().getId(),
                member.getUser().getDisplayName()
        );
    }

    private record ValidatedPosting(Account account, long balanceDelta) {
    }
}
