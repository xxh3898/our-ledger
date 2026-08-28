package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.household.Household;
import io.github.xxh3898.ourledger.household.HouseholdRepository;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.GeneratedTransactionCommand;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionService;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;

@Service
public class RecurringOccurrenceProcessor {

    private final RecurringTransactionRepository recurringRepository;
    private final RecurringTransactionAccountRepository recurringAccountRepository;
    private final LedgerTransactionRepository transactionRepository;
    private final HouseholdRepository householdRepository;
    private final TransactionService transactionService;

    public RecurringOccurrenceProcessor(
            RecurringTransactionRepository recurringRepository,
            RecurringTransactionAccountRepository recurringAccountRepository,
            LedgerTransactionRepository transactionRepository,
            HouseholdRepository householdRepository,
            TransactionService transactionService
    ) {
        this.recurringRepository = recurringRepository;
        this.recurringAccountRepository = recurringAccountRepository;
        this.transactionRepository = transactionRepository;
        this.householdRepository = householdRepository;
        this.transactionService = transactionService;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Result generateOne(Long recurringId, Instant now) {
        RecurringTransaction recurring = recurringRepository.findByIdForUpdate(recurringId)
                .orElse(null);
        if (recurring == null || !recurring.isActive()
                || recurring.getNextRecurrenceDate() == null) {
            return Result.NOT_DUE;
        }
        Household household = householdRepository.findById(recurring.getHouseholdId())
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND, ApiErrorCode.RESOURCE_NOT_FOUND));
        LocalDate recurrenceDate = recurring.getNextRecurrenceDate();
        Instant occurredAt = recurrenceDate
                .atTime(recurring.getScheduledLocalTime())
                .atZone(ZoneId.of(household.getTimezone()))
                .toInstant();
        if (occurredAt.isAfter(now)) {
            return Result.NOT_DUE;
        }

        LocalDate nextDate = RecurrenceSchedule.nextAfter(
                recurring.getStartDate(), recurring.getFrequency(),
                recurring.getIntervalValue(), recurrenceDate, recurring.getEndDate());
        if (transactionRepository.existsByGeneratedFromRecurringIdAndRecurrenceDate(
                recurring.getId(), recurrenceDate)) {
            recurring.advanceTo(nextDate);
            recurringRepository.flush();
            return Result.ALREADY_CREATED;
        }

        TemplateAccounts accounts = requireTemplateAccounts(recurring);
        transactionService.createGenerated(new GeneratedTransactionCommand(
                recurring.getHouseholdId(), recurring.getId(), recurrenceDate,
                recurring.getType(), recurring.getAmount(), recurring.getScope(),
                recurring.getOwnerMemberId(), recurring.getPayerMemberId(),
                recurring.getCategoryId(), accounts.primaryAccountId(),
                accounts.sourceAccountId(), accounts.destinationAccountId(), occurredAt,
                recurring.getMemo(), recurring.getUpdatedBy()
        ));
        recurring.advanceTo(nextDate);
        recurringRepository.flush();
        return Result.GENERATED;
    }

    private TemplateAccounts requireTemplateAccounts(RecurringTransaction recurring) {
        List<RecurringTransactionAccount> templates = recurringAccountRepository
                .findAllByRecurringTransactionIdAndHouseholdIdOrderByEntryRoleAsc(
                        recurring.getId(), recurring.getHouseholdId());
        Long primary = accountForRole(templates, EntryRole.PRIMARY);
        Long source = accountForRole(templates, EntryRole.SOURCE);
        Long destination = accountForRole(templates, EntryRole.DESTINATION);
        boolean valid = recurring.getType() == TransactionType.TRANSFER
                ? templates.size() == 2 && primary == null
                    && source != null && destination != null && !source.equals(destination)
                : templates.size() == 1 && primary != null
                    && source == null && destination == null;
        if (!valid) {
            throw new ApiException(
                    HttpStatus.CONFLICT, ApiErrorCode.RECURRING_TEMPLATE_INVALID);
        }
        return new TemplateAccounts(primary, source, destination);
    }

    private Long accountForRole(
            List<RecurringTransactionAccount> templates,
            EntryRole role
    ) {
        return templates.stream()
                .filter(template -> template.getEntryRole() == role)
                .map(RecurringTransactionAccount::getAccountId)
                .findFirst()
                .orElse(null);
    }

    public enum Result {
        GENERATED,
        ALREADY_CREATED,
        NOT_DUE;

        public boolean cursorAdvanced() {
            return this != NOT_DUE;
        }
    }

    private record TemplateAccounts(
            Long primaryAccountId,
            Long sourceAccountId,
            Long destinationAccountId
    ) {
    }
}
