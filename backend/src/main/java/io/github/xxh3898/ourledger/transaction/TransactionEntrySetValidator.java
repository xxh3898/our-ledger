package io.github.xxh3898.ourledger.transaction;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountType;

import java.util.List;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

public final class TransactionEntrySetValidator {

    private TransactionEntrySetValidator() {
    }

    public static boolean isValid(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> entries,
            Function<Long, Account> accountResolver
    ) {
        if ((transaction.getAdjustmentType() == AdjustmentType.NORMAL
                && transaction.getReversesTransactionId() != null)
                || (transaction.getAdjustmentType() == AdjustmentType.REFUND
                && (transaction.getType() != TransactionType.EXPENSE
                || transaction.getReversesTransactionId() == null))) {
            return false;
        }
        if (transaction.getType() == TransactionType.TRANSFER) {
            return isValidTransfer(transaction, entries, accountResolver);
        }
        return isValidPrimary(transaction, entries, accountResolver);
    }

    private static boolean isValidTransfer(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> entries,
            Function<Long, Account> accountResolver
    ) {
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
        Account sourceAccount = accountResolver.apply(source.getAccountId());
        Account destinationAccount = accountResolver.apply(destination.getAccountId());
        if (sourceAccount == null || destinationAccount == null) {
            return false;
        }
        long expectedDestinationDelta = destinationAccount.getNature() == AccountNature.ASSET
                ? transaction.getAmount()
                : Math.negateExact(transaction.getAmount());
        return sourceAccount.getNature() == AccountNature.ASSET
                && sourceAccount.getType() != AccountType.CREDIT_CARD
                && source.getBalanceDelta() == Math.negateExact(transaction.getAmount())
                && destination.getBalanceDelta() == expectedDestinationDelta;
    }

    private static boolean isValidPrimary(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> entries,
            Function<Long, Account> accountResolver
    ) {
        if (entries.size() != 1 || entries.getFirst().getEntryRole() != EntryRole.PRIMARY) {
            return false;
        }
        TransactionAccountEntry primary = entries.getFirst();
        Account account = accountResolver.apply(primary.getAccountId());
        if (account == null) {
            return false;
        }
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

    private static Set<EntryRole> roles(List<TransactionAccountEntry> entries) {
        return entries.stream()
                .map(TransactionAccountEntry::getEntryRole)
                .collect(Collectors.toSet());
    }

    private static TransactionAccountEntry entry(
            List<TransactionAccountEntry> entries,
            EntryRole role
    ) {
        return entries.stream()
                .filter(candidate -> candidate.getEntryRole() == role)
                .findFirst()
                .orElse(null);
    }
}
