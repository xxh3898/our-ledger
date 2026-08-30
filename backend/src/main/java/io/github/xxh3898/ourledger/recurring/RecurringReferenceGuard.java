package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class RecurringReferenceGuard {

    private final RecurringTransactionRepository recurringRepository;
    private final RecurringTransactionAccountRepository recurringAccountRepository;

    public RecurringReferenceGuard(
            RecurringTransactionRepository recurringRepository,
            RecurringTransactionAccountRepository recurringAccountRepository
    ) {
        this.recurringRepository = recurringRepository;
        this.recurringAccountRepository = recurringAccountRepository;
    }

    public void rejectAccountChange(
            Long householdId,
            Long accountId,
            AccountType requestedType,
            AccountNature requestedNature,
            boolean requestedArchived
    ) {
        List<RecurringTransactionAccountRepository.ActiveAccountUsage> usages =
                recurringAccountRepository.findActiveUsages(householdId, accountId);
        if (usages.isEmpty()) {
            return;
        }
        if (requestedArchived || usages.stream().anyMatch(
                usage -> !supports(
                        TransactionType.valueOf(usage.getTransactionType()),
                        EntryRole.valueOf(usage.getEntryRole()),
                        requestedType,
                        requestedNature))) {
            throw referenceInUse();
        }
    }

    public void rejectCategoryArchive(Long householdId, Long categoryId) {
        if (recurringRepository.existsActiveForCategory(householdId, categoryId)) {
            throw referenceInUse();
        }
    }

    public void rejectCategoryGroupArchive(Long householdId, Long groupId) {
        if (recurringRepository.existsActiveForCategoryGroup(householdId, groupId)) {
            throw referenceInUse();
        }
    }

    private boolean supports(
            TransactionType transactionType,
            EntryRole role,
            AccountType accountType,
            AccountNature nature
    ) {
        if (role == EntryRole.SOURCE) {
            return nature == AccountNature.ASSET && accountType != AccountType.CREDIT_CARD;
        }
        if (role == EntryRole.DESTINATION) {
            return nature == AccountNature.LIABILITY
                    || (nature == AccountNature.ASSET
                        && accountType != AccountType.CREDIT_CARD);
        }
        if (transactionType == TransactionType.INCOME) {
            return nature == AccountNature.ASSET && accountType != AccountType.CREDIT_CARD;
        }
        return transactionType == TransactionType.EXPENSE
                && ((nature == AccountNature.ASSET && accountType != AccountType.CREDIT_CARD)
                    || (accountType == AccountType.CREDIT_CARD
                        && nature == AccountNature.LIABILITY));
    }

    private ApiException referenceInUse() {
        return new ApiException(
                HttpStatus.CONFLICT, ApiErrorCode.RECURRING_REFERENCE_IN_USE);
    }
}
