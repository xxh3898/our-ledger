package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;

import java.time.LocalDate;
import java.time.LocalTime;

public record RecurringUpdateRequest(
        Long version,
        String name,
        TransactionType type,
        Long amount,
        TransactionScope scope,
        Long ownerMemberId,
        Long payerMemberId,
        Long categoryId,
        Long accountId,
        Long sourceAccountId,
        Long destinationAccountId,
        RecurrenceFrequency frequency,
        Integer intervalValue,
        LocalDate startDate,
        LocalDate endDate,
        LocalTime scheduledLocalTime,
        String memo,
        Boolean autoPost,
        Boolean active
) {
}
