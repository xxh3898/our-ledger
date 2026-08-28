package io.github.xxh3898.ourledger.transaction;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiErrorResponse;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryReferenceLock;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.category.CategoryType;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.ZoneId;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class TransactionService {

    private final LedgerTransactionRepository transactionRepository;
    private final TransactionAccountEntryRepository entryRepository;
    private final HouseholdMemberResolver householdMemberResolver;
    private final CategoryService categoryService;
    private final CategoryReferenceLock categoryReferenceLock;
    private final AccountService accountService;

    public TransactionService(
            LedgerTransactionRepository transactionRepository,
            TransactionAccountEntryRepository entryRepository,
            HouseholdMemberResolver householdMemberResolver,
            CategoryService categoryService,
            CategoryReferenceLock categoryReferenceLock,
            AccountService accountService
    ) {
        this.transactionRepository = transactionRepository;
        this.entryRepository = entryRepository;
        this.householdMemberResolver = householdMemberResolver;
        this.categoryService = categoryService;
        this.categoryReferenceLock = categoryReferenceLock;
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

    @Transactional(readOnly = true)
    public RefundSummaryResponse findRefunds(
            CurrentHousehold currentHousehold,
            Long originalTransactionId
    ) {
        LedgerTransaction original = requireRefundOriginal(requireTransaction(
                currentHousehold.householdId(), originalTransactionId));
        return toRefundSummary(original, activeRefunds(original));
    }

    @Transactional
    public TransactionResponse createRefund(
            CurrentHousehold currentHousehold,
            Long originalTransactionId,
            RefundCreateRequest request
    ) {
        validateRefundRequest(request);
        LedgerTransaction original = requireRefundOriginal(requireTransactionForUpdate(
                currentHousehold.householdId(), originalTransactionId));
        List<LedgerTransaction> refunds = activeRefunds(original);
        long remainingRefundableAmount = Math.subtractExact(
                original.getAmount(), refundedAmount(refunds));
        if (request.amount() > remainingRefundableAmount) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_REFUND_EXCEEDS_ORIGINAL,
                    List.of(new ApiErrorResponse.FieldError(
                            "amount",
                            "exceedsRemainingRefundableAmount",
                            "남은 환불 가능 금액 이하로 입력해야 합니다."
                    ))
            );
        }

        TransactionAccountEntry originalEntry = requireValidEntries(original).getFirst();
        Account originalAccount = accountService.requireAccount(
                original.getHouseholdId(), originalEntry.getAccountId());
        long refundDelta = originalEntry.getBalanceDelta() > 0
                ? Math.negateExact(request.amount())
                : request.amount();
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        LedgerTransaction refund = transactionRepository.saveAndFlush(LedgerTransaction.create(
                original.getHouseholdId(),
                TransactionType.EXPENSE,
                request.amount(),
                original.getScope(),
                original.getOwnerMemberId(),
                original.getPayerMemberId(),
                original.getCategoryId(),
                request.occurredAt(),
                request.memo(),
                AdjustmentType.REFUND,
                original.getId(),
                actor.getId()
        ));
        saveEntries(refund, List.of(new ExpectedEntry(
                originalAccount, EntryRole.PRIMARY, refundDelta)));
        return toResponse(refund);
    }

    @Transactional
    public TransactionResponse create(
            CurrentHousehold currentHousehold,
            TransactionCreateRequest request
    ) {
        ValidatedPosting posting = validatePosting(
                currentHousehold.householdId(),
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.accountId(),
                request.sourceAccountId(),
                request.destinationAccountId(),
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
        saveEntries(transaction, posting.entries());
        return toResponse(transaction);
    }

    @Transactional
    public void validateRecurringTemplate(
            Long householdId,
            TransactionType type,
            Long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId,
            String memo
    ) {
        if (categoryId != null) {
            categoryReferenceLock.lockCategoryAndGroup(householdId, categoryId);
        }
        validatePosting(
                householdId, type, amount, scope, ownerMemberId, payerMemberId,
                categoryId, accountId, sourceAccountId, destinationAccountId,
                Instant.EPOCH, memo, AdjustmentType.NORMAL, null);
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public Long createGenerated(GeneratedTransactionCommand command) {
        ValidatedPosting posting = validatePosting(
                command.householdId(), command.type(), command.amount(), command.scope(),
                command.ownerMemberId(), command.payerMemberId(), command.categoryId(),
                command.accountId(), command.sourceAccountId(), command.destinationAccountId(),
                command.occurredAt(), command.memo(), AdjustmentType.NORMAL, null
        );
        householdMemberResolver.require(command.householdId(), command.actorMemberId());
        LedgerTransaction transaction = transactionRepository.saveAndFlush(
                LedgerTransaction.createGenerated(
                        command.householdId(), command.type(), command.amount(), command.scope(),
                        command.ownerMemberId(), command.payerMemberId(), command.categoryId(),
                        command.occurredAt(), command.memo(), command.recurringTransactionId(),
                        command.recurrenceDate(), command.actorMemberId()
                )
        );
        saveEntries(transaction, posting.entries());
        return transaction.getId();
    }

    @Transactional
    public TransactionResponse update(
            CurrentHousehold currentHousehold,
            Long transactionId,
            TransactionUpdateRequest request
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        LedgerTransaction transaction = requireTransactionForUpdate(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, request.version());
        List<TransactionAccountEntry> currentEntries = requireValidEntries(transaction);
        if (transaction.getAdjustmentType() == AdjustmentType.REFUND) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_REFUND_UPDATE_NOT_ALLOWED
            );
        }
        if (hasActiveRefunds(transaction)) {
            validateProtectedOriginalUpdate(request);
            if (!hasSameFinancialMeaning(transaction, currentEntries, request)) {
                throw originalHasActiveRefunds();
            }
            HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
            transaction.update(
                    transaction.getType(),
                    transaction.getAmount(),
                    transaction.getScope(),
                    transaction.getOwnerMemberId(),
                    transaction.getPayerMemberId(),
                    transaction.getCategoryId(),
                    request.occurredAt(),
                    request.memo(),
                    transaction.getAdjustmentType(),
                    transaction.getReversesTransactionId(),
                    actor.getId()
            );
            transactionRepository.flush();
            return toResponse(transaction);
        }
        ValidatedPosting posting = validatePosting(
                currentHousehold.householdId(),
                request.type(),
                request.amount(),
                request.scope(),
                request.ownerMemberId(),
                request.payerMemberId(),
                request.categoryId(),
                request.accountId(),
                request.sourceAccountId(),
                request.destinationAccountId(),
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
        transactionRepository.flush();
        entryRepository.deleteAllForTransaction(
                transaction.getId(), transaction.getHouseholdId());
        entryRepository.flush();
        saveEntries(transaction, posting.entries());
        return toResponse(transaction);
    }

    @Transactional
    public void delete(
            CurrentHousehold currentHousehold,
            Long transactionId,
            Long version
    ) {
        LedgerTransaction transaction = requireTransactionForUpdate(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, version);
        requireValidEntries(transaction);
        if (transaction.getAdjustmentType() == AdjustmentType.REFUND) {
            transactionRepository.findByIdAndHouseholdIdForUpdate(
                    transaction.getReversesTransactionId(),
                    transaction.getHouseholdId()
            );
        } else if (hasActiveRefunds(transaction)) {
            throw originalHasActiveRefunds();
        }
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        transaction.delete(actor.getId());
        transactionRepository.flush();
    }

    private void validateRefundRequest(RefundCreateRequest request) {
        RequestValidator validator = new RequestValidator()
                .required(request.amount(), "amount")
                .required(request.occurredAt(), "occurredAt");
        if (request.amount() != null) {
            validator.check(request.amount() > 0,
                    "amount", "positive", "1 이상이어야 합니다.");
        }
        validateMemo(validator, request.memo());
        validator.throwIfInvalid();
    }

    private void validateProtectedOriginalUpdate(TransactionUpdateRequest request) {
        RequestValidator validator = new RequestValidator()
                .required(request.type(), "type")
                .required(request.amount(), "amount")
                .required(request.occurredAt(), "occurredAt")
                .required(request.adjustmentType(), "adjustmentType");
        if (request.amount() != null) {
            validator.check(request.amount() > 0,
                    "amount", "positive", "1 이상이어야 합니다.");
        }
        validateMemo(validator, request.memo());
        validator.throwIfInvalid();
    }

    private void validateMemo(RequestValidator validator, String memo) {
        if (memo != null) {
            validator.check(!memo.isBlank() && memo.strip().length() <= 500,
                    "memo", "size", "빈 문자열이 아닌 500자 이하여야 합니다.");
        }
    }

    private boolean hasSameFinancialMeaning(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> currentEntries,
            TransactionUpdateRequest request
    ) {
        TransactionAccountEntry primary = entry(currentEntries, EntryRole.PRIMARY);
        return request.type() == transaction.getType()
                && request.amount() != null
                && request.amount() == transaction.getAmount()
                && request.scope() == transaction.getScope()
                && Objects.equals(request.ownerMemberId(), transaction.getOwnerMemberId())
                && Objects.equals(request.payerMemberId(), transaction.getPayerMemberId())
                && Objects.equals(request.categoryId(), transaction.getCategoryId())
                && primary != null
                && Objects.equals(request.accountId(), primary.getAccountId())
                && request.sourceAccountId() == null
                && request.destinationAccountId() == null
                && request.adjustmentType() == transaction.getAdjustmentType()
                && Objects.equals(
                        request.reversesTransactionId(),
                        transaction.getReversesTransactionId()
                );
    }

    private boolean hasActiveRefunds(LedgerTransaction transaction) {
        return transactionRepository
                .existsByHouseholdIdAndReversesTransactionIdAndAdjustmentTypeAndDeletedAtIsNull(
                        transaction.getHouseholdId(),
                        transaction.getId(),
                        AdjustmentType.REFUND
                );
    }

    private List<LedgerTransaction> activeRefunds(LedgerTransaction original) {
        return transactionRepository
                .findAllByHouseholdIdAndReversesTransactionIdAndAdjustmentTypeAndDeletedAtIsNullOrderByOccurredAtDescIdDesc(
                        original.getHouseholdId(),
                        original.getId(),
                        AdjustmentType.REFUND
                );
    }

    private long refundedAmount(List<LedgerTransaction> refunds) {
        long total = 0;
        for (LedgerTransaction refund : refunds) {
            total = Math.addExact(total, refund.getAmount());
        }
        return total;
    }

    private LedgerTransaction requireRefundOriginal(LedgerTransaction transaction) {
        if (transaction.getType() != TransactionType.EXPENSE
                || transaction.getAdjustmentType() != AdjustmentType.NORMAL
                || transaction.getReversesTransactionId() != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_REFUND_ORIGINAL_REQUIRED
            );
        }
        requireValidEntries(transaction);
        return transaction;
    }

    private RefundSummaryResponse toRefundSummary(
            LedgerTransaction original,
            List<LedgerTransaction> refunds
    ) {
        long refundedAmount = refundedAmount(refunds);
        List<RefundSummaryResponse.Refund> items = refunds.stream()
                .map(refund -> {
                    requireValidEntries(refund);
                    return new RefundSummaryResponse.Refund(
                            refund.getId(),
                            refund.getAmount(),
                            refund.getOccurredAt(),
                            refund.getMemo(),
                            refund.getVersion()
                    );
                })
                .toList();
        return new RefundSummaryResponse(
                original.getId(),
                original.getAmount(),
                refundedAmount,
                Math.subtractExact(original.getAmount(), refundedAmount),
                items
        );
    }

    private ApiException originalHasActiveRefunds() {
        return new ApiException(
                HttpStatus.CONFLICT,
                ApiErrorCode.TRANSACTION_REFUND_ORIGINAL_HAS_ACTIVE_REFUNDS
        );
    }

    private void validateFilter(TransactionFilter filter) {
        if (filter.from() != null && filter.to() != null && filter.from().isAfter(filter.to())) {
            RequestValidator validator = new RequestValidator();
            validator.reject("from", "range", "from은 to보다 늦을 수 없습니다.");
            validator.throwIfInvalid();
        }
    }

    private ValidatedPosting validatePosting(
            Long householdId,
            TransactionType type,
            Long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId
    ) {
        RequestValidator validator = new RequestValidator()
                .required(type, "type")
                .required(amount, "amount")
                .required(occurredAt, "occurredAt")
                .required(adjustmentType, "adjustmentType");
        if (amount != null) {
            validator.check(amount > 0, "amount", "positive", "1 이상이어야 합니다.");
        }
        validateMemo(validator, memo);
        validator.throwIfInvalid();

        if (adjustmentType != AdjustmentType.NORMAL || reversesTransactionId != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_ADJUSTMENT_TYPE
            );
        }
        if (type == TransactionType.TRANSFER) {
            return validateTransfer(
                    householdId,
                    amount,
                    scope,
                    ownerMemberId,
                    payerMemberId,
                    categoryId,
                    accountId,
                    sourceAccountId,
                    destinationAccountId
            );
        }
        return validatePrimaryPosting(
                householdId,
                type,
                amount,
                scope,
                ownerMemberId,
                payerMemberId,
                categoryId,
                accountId,
                sourceAccountId,
                destinationAccountId
        );
    }

    private ValidatedPosting validateTransfer(
            Long householdId,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        new RequestValidator()
                .required(sourceAccountId, "sourceAccountId")
                .required(destinationAccountId, "destinationAccountId")
                .check(scope == null, "scope", "mustBeNull", "TRANSFER에는 scope를 지정하지 않습니다.")
                .check(ownerMemberId == null, "ownerMemberId", "mustBeNull", "TRANSFER에는 owner를 지정하지 않습니다.")
                .check(payerMemberId == null, "payerMemberId", "mustBeNull", "TRANSFER에는 payer를 지정하지 않습니다.")
                .check(categoryId == null, "categoryId", "mustBeNull", "TRANSFER에는 Category를 지정하지 않습니다.")
                .check(accountId == null, "accountId", "mustBeNull", "TRANSFER에는 PRIMARY Account를 지정하지 않습니다.")
                .throwIfInvalid();

        if (sourceAccountId.equals(destinationAccountId)) {
            accountService.requireAccountForPosting(
                    householdId, sourceAccountId);
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSFER_SAME_ACCOUNT_NOT_ALLOWED
            );
        }
        Account source;
        Account destination;
        if (sourceAccountId.compareTo(destinationAccountId) < 0) {
            source = accountService.requireAccountForPosting(
                    householdId, sourceAccountId);
            destination = accountService.requireAccountForPosting(
                    householdId, destinationAccountId);
        } else {
            destination = accountService.requireAccountForPosting(
                    householdId, destinationAccountId);
            source = accountService.requireAccountForPosting(
                    householdId, sourceAccountId);
        }
        requireActive(source);
        requireActive(destination);
        requireValidCreditCardNature(source);
        requireValidCreditCardNature(destination);
        if (source.getNature() != AccountNature.ASSET) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_TRANSFER_SOURCE
            );
        }

        long sourceDelta = Math.negateExact(amount);
        long destinationDelta = destination.getNature() == AccountNature.ASSET
                ? amount
                : Math.negateExact(amount);
        return new ValidatedPosting(List.of(
                new ExpectedEntry(source, EntryRole.SOURCE, sourceDelta),
                new ExpectedEntry(destination, EntryRole.DESTINATION, destinationDelta)
        ));
    }

    private ValidatedPosting validatePrimaryPosting(
            Long householdId,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        new RequestValidator()
                .required(scope, "scope")
                .required(categoryId, "categoryId")
                .required(accountId, "accountId")
                .check(sourceAccountId == null, "sourceAccountId", "mustBeNull", "INCOME/EXPENSE에는 source를 지정하지 않습니다.")
                .check(destinationAccountId == null, "destinationAccountId", "mustBeNull", "INCOME/EXPENSE에는 destination을 지정하지 않습니다.")
                .throwIfInvalid();

        validateScope(scope, ownerMemberId);
        if (type != TransactionType.EXPENSE && payerMemberId != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSACTION_INVALID_SCOPE
            );
        }
        if (ownerMemberId != null) {
            householdMemberResolver.require(householdId, ownerMemberId);
        }
        if (payerMemberId != null) {
            householdMemberResolver.require(householdId, payerMemberId);
        }

        Category category = categoryService.requireCategory(
                householdId, categoryId);
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

        Account account = accountService.requireAccountForPosting(
                householdId, accountId);
        requireActive(account);
        requireValidCreditCardNature(account);
        long balanceDelta = primaryBalanceDelta(type, amount, account);
        return new ValidatedPosting(List.of(
                new ExpectedEntry(account, EntryRole.PRIMARY, balanceDelta)
        ));
    }

    private long primaryBalanceDelta(TransactionType type, long amount, Account account) {
        if (type == TransactionType.INCOME) {
            if (account.getNature() != AccountNature.ASSET
                    || account.getType() == AccountType.CREDIT_CARD) {
                throw unsupportedAccountPosting();
            }
            return amount;
        }
        if (account.getType() == AccountType.CREDIT_CARD
                && account.getNature() == AccountNature.LIABILITY) {
            return amount;
        }
        if (account.getNature() == AccountNature.ASSET
                && account.getType() != AccountType.CREDIT_CARD) {
            return Math.negateExact(amount);
        }
        throw unsupportedAccountPosting();
    }

    private ApiException unsupportedAccountPosting() {
        return new ApiException(
                HttpStatus.UNPROCESSABLE_ENTITY,
                ApiErrorCode.UNSUPPORTED_ACCOUNT_POSTING
        );
    }

    private void requireActive(Account account) {
        if (account.isArchived()) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.ARCHIVED_ACCOUNT_NOT_ALLOWED
            );
        }
    }

    private void requireValidCreditCardNature(Account account) {
        if (account.getType() == AccountType.CREDIT_CARD
                && account.getNature() != AccountNature.LIABILITY) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.CREDIT_CARD_NATURE_REQUIRED
            );
        }
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

    private void saveEntries(
            LedgerTransaction transaction,
            List<ExpectedEntry> expectedEntries
    ) {
        List<TransactionAccountEntry> entries = expectedEntries.stream()
                .map(expected -> TransactionAccountEntry.create(
                        transaction.getHouseholdId(),
                        transaction.getId(),
                        expected.account().getId(),
                        expected.role(),
                        expected.balanceDelta()
                ))
                .toList();
        entryRepository.saveAllAndFlush(entries);
    }

    private LedgerTransaction requireTransaction(Long householdId, Long transactionId) {
        return transactionRepository.findByIdAndHouseholdIdAndDeletedAtIsNull(
                        transactionId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private LedgerTransaction requireTransactionForUpdate(Long householdId, Long transactionId) {
        return transactionRepository.findActiveByIdAndHouseholdIdForUpdate(
                        transactionId, householdId)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        ApiErrorCode.RESOURCE_NOT_FOUND
                ));
    }

    private List<TransactionAccountEntry> requireValidEntries(LedgerTransaction transaction) {
        List<TransactionAccountEntry> entries = entryRepository
                .findAllByTransactionIdAndHouseholdId(
                        transaction.getId(), transaction.getHouseholdId())
                .stream()
                .sorted(Comparator.comparingInt(entry -> entry.getEntryRole().ordinal()))
                .toList();
        if (!hasValidEntrySet(transaction, entries)) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID
            );
        }
        return entries;
    }

    private boolean hasValidEntrySet(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> entries
    ) {
        if ((transaction.getAdjustmentType() == AdjustmentType.NORMAL
                && transaction.getReversesTransactionId() != null)
                || (transaction.getAdjustmentType() == AdjustmentType.REFUND
                && (transaction.getType() != TransactionType.EXPENSE
                || transaction.getReversesTransactionId() == null))) {
            return false;
        }
        if (transaction.getType() == TransactionType.TRANSFER) {
            if (transaction.getAdjustmentType() != AdjustmentType.NORMAL) {
                return false;
            }
            if (entries.size() != 2 || roles(entries).size() != 2) {
                return false;
            }
            TransactionAccountEntry source = entry(entries, EntryRole.SOURCE);
            TransactionAccountEntry destination = entry(entries, EntryRole.DESTINATION);
            if (source == null || destination == null
                    || source.getAccountId().equals(destination.getAccountId())) {
                return false;
            }
            Account sourceAccount = accountService.requireAccount(
                    transaction.getHouseholdId(), source.getAccountId());
            Account destinationAccount = accountService.requireAccount(
                    transaction.getHouseholdId(), destination.getAccountId());
            long expectedDestinationDelta = destinationAccount.getNature() == AccountNature.ASSET
                    ? transaction.getAmount()
                    : Math.negateExact(transaction.getAmount());
            return sourceAccount.getNature() == AccountNature.ASSET
                    && sourceAccount.getType() != AccountType.CREDIT_CARD
                    && source.getBalanceDelta() == Math.negateExact(transaction.getAmount())
                    && destination.getBalanceDelta() == expectedDestinationDelta;
        }

        if (entries.size() != 1 || entries.getFirst().getEntryRole() != EntryRole.PRIMARY) {
            return false;
        }
        TransactionAccountEntry primary = entries.getFirst();
        Account account = accountService.requireAccount(
                transaction.getHouseholdId(), primary.getAccountId());
        long expectedDelta;
        if (transaction.getType() == TransactionType.INCOME
                && account.getNature() == AccountNature.ASSET
                && account.getType() != AccountType.CREDIT_CARD) {
            expectedDelta = transaction.getAmount();
        } else if (transaction.getType() == TransactionType.EXPENSE
                && account.getType() == AccountType.CREDIT_CARD
                && account.getNature() == AccountNature.LIABILITY) {
            expectedDelta = transaction.getAmount();
        } else if (transaction.getType() == TransactionType.EXPENSE
                && account.getNature() == AccountNature.ASSET
                && account.getType() != AccountType.CREDIT_CARD) {
            expectedDelta = Math.negateExact(transaction.getAmount());
        } else {
            return false;
        }
        if (transaction.getAdjustmentType() == AdjustmentType.REFUND) {
            expectedDelta = Math.negateExact(expectedDelta);
        }
        return primary.getBalanceDelta() == expectedDelta;
    }

    private Set<EntryRole> roles(List<TransactionAccountEntry> entries) {
        return entries.stream()
                .map(TransactionAccountEntry::getEntryRole)
                .collect(Collectors.toSet());
    }

    private TransactionAccountEntry entry(
            List<TransactionAccountEntry> entries,
            EntryRole role
    ) {
        return entries.stream()
                .filter(entry -> entry.getEntryRole() == role)
                .findFirst()
                .orElse(null);
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
        Category category = transaction.getCategoryId() == null
                ? null
                : categoryService.requireCategory(
                        transaction.getHouseholdId(), transaction.getCategoryId());
        List<TransactionResponse.Entry> entries = requireValidEntries(transaction).stream()
                .map(entry -> {
                    Account account = accountService.requireAccount(
                            transaction.getHouseholdId(), entry.getAccountId());
                    return new TransactionResponse.Entry(
                            entry.getId(),
                            entry.getEntryRole(),
                            entry.getBalanceDelta(),
                            toAccountReference(account)
                    );
                })
                .toList();
        return new TransactionResponse(
                transaction.getId(),
                transaction.getType(),
                transaction.getAmount(),
                transaction.getScope(),
                toMember(owner),
                toMember(payer),
                toCategoryReference(category),
                transaction.getOccurredAt(),
                transaction.getMemo(),
                transaction.getAdjustmentType(),
                transaction.getGeneratedFromRecurringId(),
                transaction.getRecurrenceDate(),
                transaction.getVersion(),
                entries,
                transaction.getCreatedAt(),
                transaction.getUpdatedAt()
        );
    }

    private TransactionResponse.CategoryReference toCategoryReference(Category category) {
        if (category == null) {
            return null;
        }
        return new TransactionResponse.CategoryReference(
                category.getId(),
                category.getName(),
                category.getType(),
                categoryService.isEffectivelyArchived(category)
        );
    }

    private TransactionResponse.AccountReference toAccountReference(Account account) {
        return new TransactionResponse.AccountReference(
                account.getId(),
                account.getName(),
                account.getType(),
                account.getNature(),
                account.isArchived()
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

    private record ExpectedEntry(Account account, EntryRole role, long balanceDelta) {
    }

    private record ValidatedPosting(List<ExpectedEntry> entries) {
        private ValidatedPosting {
            entries = List.copyOf(entries);
        }
    }
}
