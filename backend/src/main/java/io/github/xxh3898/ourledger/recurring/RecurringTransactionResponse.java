package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.account.AccountNature;
import io.github.xxh3898.ourledger.account.AccountType;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;

public record RecurringTransactionResponse(
        Long id,
        String name,
        TransactionType type,
        long amount,
        TransactionScope scope,
        Member owner,
        Member payer,
        CategoryReference category,
        List<AccountTemplate> accounts,
        RecurrenceFrequency frequency,
        int intervalValue,
        LocalDate startDate,
        LocalDate endDate,
        LocalTime scheduledLocalTime,
        String memo,
        boolean autoPost,
        boolean active,
        LocalDate nextRecurrenceDate,
        RecurringStatus status,
        long version,
        Instant createdAt,
        Instant updatedAt
) {

    public record Member(Long memberId, String displayName) {
    }

    public record CategoryReference(Long id, String name, boolean archived) {
    }

    public record AccountTemplate(EntryRole role, AccountReference account) {
    }

    public record AccountReference(
            Long id,
            String name,
            AccountType type,
            AccountNature nature,
            boolean archived
    ) {
    }
}
