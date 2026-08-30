package io.github.xxh3898.ourledger.calendar;

import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.NetSpendingCalculator;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.YearMonth;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Service
public class CalendarService {

    private final LedgerTransactionRepository transactionRepository;
    private final HouseholdMemberResolver householdMemberResolver;

    public CalendarService(
            LedgerTransactionRepository transactionRepository,
            HouseholdMemberResolver householdMemberResolver
    ) {
        this.transactionRepository = transactionRepository;
        this.householdMemberResolver = householdMemberResolver;
    }

    @Transactional(readOnly = true)
    public CalendarMonthResponse findMonth(
            CurrentHousehold currentHousehold,
            YearMonth month,
            TransactionScope scope,
            Long ownerMemberId
    ) {
        validateFilter(currentHousehold, month, scope, ownerMemberId);

        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        YearMonth previousMonth = month.minusMonths(1);
        var fromInclusive = previousMonth.atDay(1).atStartOfDay(zoneId).toInstant();
        var toExclusive = month.plusMonths(1).atDay(1).atStartOfDay(zoneId).toInstant();
        List<LedgerTransaction> transactions = transactionRepository
                .findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                        currentHousehold.householdId(),
                        fromInclusive,
                        toExclusive
                )
                .stream()
                .filter(transaction -> matchesScope(transaction, scope, ownerMemberId))
                .toList();

        long currentNetSpending = 0;
        long previousNetSpending = 0;
        Map<LocalDate, MutableDay> currentDays = new LinkedHashMap<>();
        for (LedgerTransaction transaction : transactions) {
            LocalDate occurredOn = transaction.getOccurredAt().atZone(zoneId).toLocalDate();
            YearMonth occurredMonth = YearMonth.from(occurredOn);
            long netSpending = NetSpendingCalculator.amountOf(transaction);
            if (month.equals(occurredMonth)) {
                currentNetSpending = Math.addExact(currentNetSpending, netSpending);
                currentDays.computeIfAbsent(occurredOn, ignored -> new MutableDay())
                        .add(netSpending);
            } else if (previousMonth.equals(occurredMonth)) {
                previousNetSpending = Math.addExact(previousNetSpending, netSpending);
            }
        }

        List<CalendarMonthResponse.Day> days = new ArrayList<>(currentDays.size());
        currentDays.entrySet().stream()
                .sorted(Map.Entry.comparingByKey(Comparator.naturalOrder()))
                .forEach(entry -> days.add(new CalendarMonthResponse.Day(
                        entry.getKey(),
                        entry.getValue().transactionCount,
                        entry.getValue().netSpendingAmount
                )));

        return new CalendarMonthResponse(
                month,
                zoneId.getId(),
                new CalendarMonthResponse.Summary(
                        currentNetSpending,
                        previousNetSpending,
                        Math.subtractExact(currentNetSpending, previousNetSpending)
                ),
                days
        );
    }

    private void validateFilter(
            CurrentHousehold currentHousehold,
            YearMonth month,
            TransactionScope scope,
            Long ownerMemberId
    ) {
        RequestValidator validator = new RequestValidator().required(month, "month");
        if (scope == null) {
            validator.check(
                    ownerMemberId == null,
                    "ownerMemberId",
                    "unexpected",
                    "scope 없이 ownerMemberId를 지정할 수 없습니다."
            );
        } else if (scope == TransactionScope.PERSONAL) {
            validator.required(ownerMemberId, "ownerMemberId");
        } else {
            validator.check(
                    ownerMemberId == null,
                    "ownerMemberId",
                    "unexpected",
                    "SHARED scope에는 ownerMemberId를 지정할 수 없습니다."
            );
        }
        validator.throwIfInvalid();

        if (scope == TransactionScope.PERSONAL) {
            householdMemberResolver.require(currentHousehold.householdId(), ownerMemberId);
        }
    }

    private boolean matchesScope(
            LedgerTransaction transaction,
            TransactionScope scope,
            Long ownerMemberId
    ) {
        if (scope == null) {
            return true;
        }
        if (scope == TransactionScope.SHARED) {
            return transaction.getScope() == TransactionScope.SHARED;
        }
        return transaction.getScope() == TransactionScope.PERSONAL
                && Objects.equals(transaction.getOwnerMemberId(), ownerMemberId);
    }

    private static final class MutableDay {

        private long transactionCount;
        private long netSpendingAmount;

        private void add(long netSpending) {
            transactionCount = Math.incrementExact(transactionCount);
            netSpendingAmount = Math.addExact(netSpendingAmount, netSpending);
        }
    }
}
