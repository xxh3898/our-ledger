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
import java.time.ZoneId;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

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
    public TransactionResponse update(
            CurrentHousehold currentHousehold,
            Long transactionId,
            TransactionUpdateRequest request
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        LedgerTransaction transaction = requireTransaction(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, request.version());
        requireValidEntries(transaction);
        ValidatedPosting posting = validatePosting(
                currentHousehold,
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
        LedgerTransaction transaction = requireTransaction(
                currentHousehold.householdId(), transactionId);
        rejectStaleVersion(transaction, version);
        requireValidEntries(transaction);
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
        if (memo != null) {
            validator.check(!memo.isBlank() && memo.strip().length() <= 500,
                    "memo", "size", "빈 문자열이 아닌 500자 이하여야 합니다.");
        }
        validator.throwIfInvalid();

        if (adjustmentType != AdjustmentType.NORMAL || reversesTransactionId != null) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.UNSUPPORTED_ADJUSTMENT_TYPE
            );
        }
        if (type == TransactionType.TRANSFER) {
            return validateTransfer(
                    currentHousehold,
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
                currentHousehold,
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
            CurrentHousehold currentHousehold,
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
                    currentHousehold.householdId(), sourceAccountId);
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.TRANSFER_SAME_ACCOUNT_NOT_ALLOWED
            );
        }
        Account source;
        Account destination;
        if (sourceAccountId.compareTo(destinationAccountId) < 0) {
            source = accountService.requireAccountForPosting(
                    currentHousehold.householdId(), sourceAccountId);
            destination = accountService.requireAccountForPosting(
                    currentHousehold.householdId(), destinationAccountId);
        } else {
            destination = accountService.requireAccountForPosting(
                    currentHousehold.householdId(), destinationAccountId);
            source = accountService.requireAccountForPosting(
                    currentHousehold.householdId(), sourceAccountId);
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
            CurrentHousehold currentHousehold,
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

        Account account = accountService.requireAccountForPosting(
                currentHousehold.householdId(), accountId);
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
        if (transaction.getType() == TransactionType.TRANSFER) {
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
