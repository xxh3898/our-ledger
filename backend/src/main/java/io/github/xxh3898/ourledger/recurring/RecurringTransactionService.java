package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountService;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiErrorResponse;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

@Service
public class RecurringTransactionService {

    private final RecurringTransactionRepository recurringRepository;
    private final RecurringTransactionAccountRepository recurringAccountRepository;
    private final HouseholdMemberResolver householdMemberResolver;
    private final AccountService accountService;
    private final CategoryService categoryService;
    private final TransactionService transactionService;
    private final Clock clock;

    public RecurringTransactionService(
            RecurringTransactionRepository recurringRepository,
            RecurringTransactionAccountRepository recurringAccountRepository,
            HouseholdMemberResolver householdMemberResolver,
            AccountService accountService,
            CategoryService categoryService,
            TransactionService transactionService,
            Clock clock
    ) {
        this.recurringRepository = recurringRepository;
        this.recurringAccountRepository = recurringAccountRepository;
        this.householdMemberResolver = householdMemberResolver;
        this.accountService = accountService;
        this.categoryService = categoryService;
        this.transactionService = transactionService;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<RecurringTransactionResponse> findAll(CurrentHousehold currentHousehold) {
        return recurringRepository.findAllByHouseholdIdOrderByIdAsc(
                        currentHousehold.householdId())
                .stream()
                .map(this::toResponse)
                .toList();
    }

    @Transactional
    public RecurringTransactionResponse create(
            CurrentHousehold currentHousehold,
            RecurringCreateRequest request
    ) {
        return createAt(currentHousehold, request, clock.instant());
    }

    @Transactional
    public RecurringTransactionResponse createAt(
            CurrentHousehold currentHousehold,
            RecurringCreateRequest request,
            Instant now
    ) {
        validateRequest(
                request.name(), request.type(), request.amount(), request.frequency(),
                request.intervalValue(), request.startDate(), request.endDate(),
                request.scheduledLocalTime(), request.memo(), request.autoPost(),
                request.active(), localToday(currentHousehold, now), true
        );
        validateTemplate(
                currentHousehold.householdId(), request.type(), request.amount(), request.scope(),
                request.ownerMemberId(), request.payerMemberId(), request.categoryId(),
                request.accountId(), request.sourceAccountId(), request.destinationAccountId(),
                request.memo()
        );
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        LocalDate nextDate = boundedStart(request.startDate(), request.endDate());
        RecurringTransaction recurring = recurringRepository.saveAndFlush(
                RecurringTransaction.create(
                        currentHousehold.householdId(), request.name(), request.type(),
                        request.amount(), request.scope(), request.ownerMemberId(),
                        request.payerMemberId(), request.categoryId(), request.memo(),
                        request.frequency(), request.intervalValue(), request.startDate(),
                        request.endDate(), request.scheduledLocalTime(), request.autoPost(),
                        request.active(), nextDate, actor.getId()
                )
        );
        replaceAccounts(
                recurring,
                request.accountId(), request.sourceAccountId(), request.destinationAccountId());
        return toResponse(recurring);
    }

    @Transactional
    public RecurringTransactionResponse update(
            CurrentHousehold currentHousehold,
            Long recurringId,
            RecurringUpdateRequest request
    ) {
        return updateAt(currentHousehold, recurringId, request, clock.instant());
    }

    @Transactional
    public RecurringTransactionResponse updateAt(
            CurrentHousehold currentHousehold,
            Long recurringId,
            RecurringUpdateRequest request,
            Instant now
    ) {
        new RequestValidator().required(request.version(), "version").throwIfInvalid();
        RecurringTransaction recurring = recurringRepository
                .findByIdAndHouseholdIdForUpdate(recurringId, currentHousehold.householdId())
                .orElseThrow(this::notFound);
        if (request.version() == null || recurring.getVersion() != request.version()) {
            throw new ApiException(
                    HttpStatus.CONFLICT, ApiErrorCode.RECURRING_VERSION_CONFLICT);
        }

        LocalDate today = localToday(currentHousehold, now);
        boolean startChanged = !Objects.equals(recurring.getStartDate(), request.startDate());
        validateRequest(
                request.name(), request.type(), request.amount(), request.frequency(),
                request.intervalValue(), request.startDate(), request.endDate(),
                request.scheduledLocalTime(), request.memo(), request.autoPost(),
                request.active(), today, startChanged
        );
        validateTemplate(
                currentHousehold.householdId(), request.type(), request.amount(), request.scope(),
                request.ownerMemberId(), request.payerMemberId(), request.categoryId(),
                request.accountId(), request.sourceAccountId(), request.destinationAccountId(),
                request.memo()
        );
        HouseholdMember actor = householdMemberResolver.requireCurrent(currentHousehold);
        LocalDate nextDate = nextDateAfterUpdate(recurring, request, currentHousehold, now);
        recurring.update(
                request.name(), request.type(), request.amount(), request.scope(),
                request.ownerMemberId(), request.payerMemberId(), request.categoryId(),
                request.memo(), request.frequency(), request.intervalValue(), request.startDate(),
                request.endDate(), request.scheduledLocalTime(), request.autoPost(),
                request.active(), nextDate, actor.getId()
        );
        recurringRepository.flush();
        replaceAccounts(
                recurring,
                request.accountId(), request.sourceAccountId(), request.destinationAccountId());
        return toResponse(recurring);
    }

    private void validateRequest(
            String name,
            TransactionType type,
            Long amount,
            RecurrenceFrequency frequency,
            Integer intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            java.time.LocalTime scheduledLocalTime,
            String memo,
            Boolean autoPost,
            Boolean active,
            LocalDate today,
            boolean enforceStartToday
    ) {
        RequestValidator validator = new RequestValidator()
                .requiredText(name, "name")
                .required(type, "type")
                .required(amount, "amount")
                .required(frequency, "frequency")
                .required(intervalValue, "intervalValue")
                .required(startDate, "startDate")
                .required(scheduledLocalTime, "scheduledLocalTime")
                .required(autoPost, "autoPost")
                .required(active, "active");
        if (name != null) {
            validator.check(name.strip().length() <= 100,
                    "name", "size", "100자 이하여야 합니다.");
        }
        if (amount != null) {
            validator.check(amount > 0, "amount", "positive", "1 이상이어야 합니다.");
        }
        if (intervalValue != null) {
            validator.check(intervalValue > 0,
                    "intervalValue", "positive", "1 이상이어야 합니다.");
        }
        if (startDate != null && enforceStartToday) {
            validator.check(!startDate.isBefore(today),
                    "startDate", "notPast", "Household의 오늘보다 이전일 수 없습니다.");
        }
        if (startDate != null && endDate != null) {
            validator.check(!endDate.isBefore(startDate),
                    "endDate", "range", "startDate보다 이전일 수 없습니다.");
        }
        if (memo != null) {
            validator.check(!memo.isBlank() && memo.strip().length() <= 500,
                    "memo", "size", "빈 문자열이 아닌 500자 이하여야 합니다.");
        }
        validator.throwIfInvalid();
        if (!Boolean.TRUE.equals(autoPost)) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.RECURRING_AUTO_POST_REQUIRED,
                    List.of(new ApiErrorResponse.FieldError(
                            "autoPost", "supported", "V1에서는 true만 지원합니다."))
            );
        }
    }

    private void validateTemplate(
            Long householdId,
            TransactionType type,
            Long amount,
            io.github.xxh3898.ourledger.transaction.TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId,
            String memo
    ) {
        transactionService.validateRecurringTemplate(
                householdId, type, amount, scope, ownerMemberId, payerMemberId,
                categoryId, accountId, sourceAccountId, destinationAccountId, memo);
    }

    private LocalDate nextDateAfterUpdate(
            RecurringTransaction recurring,
            RecurringUpdateRequest request,
            CurrentHousehold currentHousehold,
            Instant now
    ) {
        if (!request.active()) {
            return recurring.getNextRecurrenceDate();
        }
        boolean resumed = !recurring.isActive();
        boolean scheduleChanged = recurring.getFrequency() != request.frequency()
                || recurring.getIntervalValue() != request.intervalValue()
                || !Objects.equals(recurring.getStartDate(), request.startDate())
                || !Objects.equals(
                        recurring.getScheduledLocalTime(), request.scheduledLocalTime());
        boolean endChanged = !Objects.equals(recurring.getEndDate(), request.endDate());
        if (resumed || scheduleChanged) {
            return firstFutureDate(request, currentHousehold, now);
        }
        if (endChanged) {
            LocalDate current = recurring.getNextRecurrenceDate();
            if (current != null
                    && (request.endDate() == null || !current.isAfter(request.endDate()))) {
                return current;
            }
            return firstFutureDate(request, currentHousehold, now);
        }
        return recurring.getNextRecurrenceDate();
    }

    private LocalDate firstFutureDate(
            RecurringUpdateRequest request,
            CurrentHousehold currentHousehold,
            Instant now
    ) {
        return RecurrenceSchedule.firstAfterInstant(
                request.startDate(), request.frequency(), request.intervalValue(),
                request.endDate(), request.scheduledLocalTime(),
                ZoneId.of(currentHousehold.timezone()), now);
    }

    private LocalDate boundedStart(LocalDate startDate, LocalDate endDate) {
        return endDate != null && startDate.isAfter(endDate) ? null : startDate;
    }

    private LocalDate localToday(CurrentHousehold currentHousehold, Instant now) {
        return now.atZone(ZoneId.of(currentHousehold.timezone())).toLocalDate();
    }

    private void replaceAccounts(
            RecurringTransaction recurring,
            Long accountId,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
        recurringAccountRepository.deleteAllForRule(
                recurring.getId(), recurring.getHouseholdId());
        recurringAccountRepository.flush();
        List<RecurringTransactionAccount> accounts = new ArrayList<>();
        if (recurring.getType() == TransactionType.TRANSFER) {
            accounts.add(RecurringTransactionAccount.create(
                    recurring.getHouseholdId(), recurring.getId(),
                    sourceAccountId, EntryRole.SOURCE));
            accounts.add(RecurringTransactionAccount.create(
                    recurring.getHouseholdId(), recurring.getId(),
                    destinationAccountId, EntryRole.DESTINATION));
        } else {
            accounts.add(RecurringTransactionAccount.create(
                    recurring.getHouseholdId(), recurring.getId(),
                    accountId, EntryRole.PRIMARY));
        }
        recurringAccountRepository.saveAllAndFlush(accounts);
    }

    private RecurringTransactionResponse toResponse(RecurringTransaction recurring) {
        HouseholdMember owner = recurring.getOwnerMemberId() == null ? null
                : householdMemberResolver.require(
                        recurring.getHouseholdId(), recurring.getOwnerMemberId());
        HouseholdMember payer = recurring.getPayerMemberId() == null ? null
                : householdMemberResolver.require(
                        recurring.getHouseholdId(), recurring.getPayerMemberId());
        Category category = recurring.getCategoryId() == null ? null
                : categoryService.requireCategory(
                        recurring.getHouseholdId(), recurring.getCategoryId());
        List<RecurringTransactionResponse.AccountTemplate> accounts =
                recurringAccountRepository
                        .findAllByRecurringTransactionIdAndHouseholdIdOrderByEntryRoleAsc(
                                recurring.getId(), recurring.getHouseholdId())
                        .stream()
                        .sorted(Comparator.comparingInt(
                                account -> account.getEntryRole().ordinal()))
                        .map(template -> {
                            Account account = accountService.requireAccount(
                                    recurring.getHouseholdId(), template.getAccountId());
                            return new RecurringTransactionResponse.AccountTemplate(
                                    template.getEntryRole(),
                                    new RecurringTransactionResponse.AccountReference(
                                            account.getId(), account.getName(), account.getType(),
                                            account.getNature(), account.isArchived())
                            );
                        })
                        .toList();
        RecurringStatus status = !recurring.isActive()
                ? RecurringStatus.PAUSED
                : recurring.getNextRecurrenceDate() == null
                    ? RecurringStatus.ENDED
                    : RecurringStatus.ACTIVE;
        return new RecurringTransactionResponse(
                recurring.getId(), recurring.getName(), recurring.getType(),
                recurring.getAmount(), recurring.getScope(), toMember(owner), toMember(payer),
                category == null ? null : new RecurringTransactionResponse.CategoryReference(
                        category.getId(), category.getName(),
                        categoryService.isEffectivelyArchived(category)),
                accounts, recurring.getFrequency(), recurring.getIntervalValue(),
                recurring.getStartDate(), recurring.getEndDate(),
                recurring.getScheduledLocalTime(), recurring.getMemo(), recurring.isAutoPost(),
                recurring.isActive(), recurring.getNextRecurrenceDate(), status,
                recurring.getVersion(), recurring.getCreatedAt(), recurring.getUpdatedAt()
        );
    }

    private RecurringTransactionResponse.Member toMember(HouseholdMember member) {
        return member == null ? null : new RecurringTransactionResponse.Member(
                member.getId(), member.getUser().getDisplayName());
    }

    private ApiException notFound() {
        return new ApiException(HttpStatus.NOT_FOUND, ApiErrorCode.RESOURCE_NOT_FOUND);
    }
}
