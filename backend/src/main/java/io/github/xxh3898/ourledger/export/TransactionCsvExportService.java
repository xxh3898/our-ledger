package io.github.xxh3898.ourledger.export;

import io.github.xxh3898.ourledger.account.Account;
import io.github.xxh3898.ourledger.account.AccountRepository;
import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.api.RequestValidator;
import io.github.xxh3898.ourledger.category.Category;
import io.github.xxh3898.ourledger.category.CategoryRepository;
import io.github.xxh3898.ourledger.household.HouseholdMember;
import io.github.xxh3898.ourledger.household.HouseholdMemberRepository;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.AdjustmentType;
import io.github.xxh3898.ourledger.transaction.EntryRole;
import io.github.xxh3898.ourledger.transaction.LedgerTransaction;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntry;
import io.github.xxh3898.ourledger.transaction.TransactionAccountEntryRepository;
import io.github.xxh3898.ourledger.transaction.TransactionEntrySetValidator;
import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class TransactionCsvExportService {

    static final long MAX_RANGE_DAYS = 3_653;

    private static final List<String> HEADER = List.of(
            "거래ID",
            "발생일",
            "발생시각",
            "거래유형",
            "조정유형",
            "금액",
            "귀속",
            "소유자",
            "결제자",
            "카테고리",
            "계좌",
            "출금계좌",
            "입금계좌",
            "메모",
            "원거래ID",
            "반복거래",
            "반복발생일",
            "생성시각",
            "수정시각"
    );

    private final LedgerTransactionRepository transactionRepository;
    private final TransactionAccountEntryRepository entryRepository;
    private final AccountRepository accountRepository;
    private final CategoryRepository categoryRepository;
    private final HouseholdMemberRepository householdMemberRepository;

    public TransactionCsvExportService(
            LedgerTransactionRepository transactionRepository,
            TransactionAccountEntryRepository entryRepository,
            AccountRepository accountRepository,
            CategoryRepository categoryRepository,
            HouseholdMemberRepository householdMemberRepository
    ) {
        this.transactionRepository = transactionRepository;
        this.entryRepository = entryRepository;
        this.accountRepository = accountRepository;
        this.categoryRepository = categoryRepository;
        this.householdMemberRepository = householdMemberRepository;
    }

    @Transactional(readOnly = true)
    public TransactionCsvDocument export(
            CurrentHousehold currentHousehold,
            LocalDate from,
            LocalDate to
    ) {
        validateRange(from, to);
        ZoneId zoneId = ZoneId.of(currentHousehold.timezone());
        Instant fromInclusive;
        Instant toExclusive;
        try {
            fromInclusive = from.atStartOfDay(zoneId).toInstant();
            toExclusive = to.plusDays(1).atStartOfDay(zoneId).toInstant();
        } catch (DateTimeException exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, ApiErrorCode.INVALID_REQUEST);
        }

        List<LedgerTransaction> transactions = transactionRepository
                .findAllByHouseholdIdAndDeletedAtIsNullAndOccurredAtGreaterThanEqualAndOccurredAtLessThanOrderByOccurredAtAscIdAsc(
                        currentHousehold.householdId(), fromInclusive, toExclusive);

        List<List<String>> rows = new ArrayList<>();
        rows.add(HEADER);
        if (!transactions.isEmpty()) {
            appendTransactionRows(rows, currentHousehold.householdId(), zoneId, transactions);
        }
        return new TransactionCsvDocument(
                Rfc4180CsvWriter.write(rows),
                "our-ledger-transactions_%s_%s.csv".formatted(from, to)
        );
    }

    private void validateRange(LocalDate from, LocalDate to) {
        RequestValidator validator = new RequestValidator()
                .required(from, "from")
                .required(to, "to");
        if (from != null && to != null) {
            validator.check(!from.isAfter(to), "to", "invalidRange",
                    "종료일은 시작일보다 빠를 수 없습니다.");
        }
        validator.throwIfInvalid();

        long inclusiveDays = ChronoUnit.DAYS.between(from, to) + 1;
        if (inclusiveDays > MAX_RANGE_DAYS) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    ApiErrorCode.EXPORT_RANGE_TOO_LARGE
            );
        }
    }

    private void appendTransactionRows(
            List<List<String>> rows,
            Long householdId,
            ZoneId zoneId,
            List<LedgerTransaction> transactions
    ) {
        Set<Long> transactionIds = transactions.stream()
                .map(LedgerTransaction::getId)
                .collect(Collectors.toSet());
        Map<Long, List<TransactionAccountEntry>> entriesByTransaction = entryRepository
                .findAllByHouseholdIdAndTransactionIdInOrderByTransactionIdAscIdAsc(
                        householdId, transactionIds)
                .stream()
                .collect(Collectors.groupingBy(TransactionAccountEntry::getTransactionId));
        Map<Long, Account> accounts = accountRepository
                .findAllByHouseholdIdOrderBySortOrderAscIdAsc(householdId)
                .stream()
                .collect(Collectors.toMap(Account::getId, Function.identity()));
        Map<Long, Category> categories = categoryRepository
                .findAllByHouseholdIdOrderByTypeAscSortOrderAscIdAsc(householdId)
                .stream()
                .collect(Collectors.toMap(Category::getId, Function.identity()));
        Map<Long, HouseholdMember> members = householdMemberRepository
                .findAllByHousehold_IdOrderByJoinedAtAscIdAsc(householdId)
                .stream()
                .collect(Collectors.toMap(HouseholdMember::getId, Function.identity()));

        for (LedgerTransaction transaction : transactions) {
            List<TransactionAccountEntry> entries = entriesByTransaction
                    .getOrDefault(transaction.getId(), List.of());
            if (!TransactionEntrySetValidator.isValid(transaction, entries, accounts::get)
                    || !hasValidReferences(transaction, categories, members)) {
                throw invalidEntrySet();
            }
            rows.add(toRow(transaction, entries, accounts, categories, members, zoneId));
        }
    }

    private boolean hasValidReferences(
            LedgerTransaction transaction,
            Map<Long, Category> categories,
            Map<Long, HouseholdMember> members
    ) {
        if (transaction.getType() != TransactionType.TRANSFER
                && !categories.containsKey(transaction.getCategoryId())) {
            return false;
        }
        if (transaction.getScope() == TransactionScope.PERSONAL
                && !members.containsKey(transaction.getOwnerMemberId())) {
            return false;
        }
        return transaction.getPayerMemberId() == null
                || members.containsKey(transaction.getPayerMemberId());
    }

    private List<String> toRow(
            LedgerTransaction transaction,
            List<TransactionAccountEntry> entries,
            Map<Long, Account> accounts,
            Map<Long, Category> categories,
            Map<Long, HouseholdMember> members,
            ZoneId zoneId
    ) {
        TransactionAccountEntry primary = entry(entries, EntryRole.PRIMARY);
        TransactionAccountEntry source = entry(entries, EntryRole.SOURCE);
        TransactionAccountEntry destination = entry(entries, EntryRole.DESTINATION);
        var occurredAt = transaction.getOccurredAt().atZone(zoneId).toOffsetDateTime();

        return List.of(
                transaction.getId().toString(),
                occurredAt.toLocalDate().toString(),
                occurredAt.toString(),
                transactionType(transaction.getType()),
                adjustmentType(transaction.getAdjustmentType()),
                Long.toString(transaction.getAmount()),
                scope(transaction),
                text(memberName(transaction.getOwnerMemberId(), members,
                        transaction.getScope() == TransactionScope.PERSONAL)),
                text(memberName(transaction.getPayerMemberId(), members,
                        transaction.getType() == TransactionType.EXPENSE)),
                text(referenceName(transaction.getCategoryId(), categories)),
                text(accountName(primary, accounts)),
                text(accountName(source, accounts)),
                text(accountName(destination, accounts)),
                text(transaction.getMemo()),
                nullableId(transaction.getReversesTransactionId()),
                transaction.getGeneratedFromRecurringId() == null ? "아니오" : "예",
                transaction.getRecurrenceDate() == null
                        ? ""
                        : transaction.getRecurrenceDate().toString(),
                transaction.getCreatedAt().toString(),
                transaction.getUpdatedAt().toString()
        );
    }

    private String transactionType(TransactionType type) {
        return switch (type) {
            case INCOME -> "수입";
            case EXPENSE -> "지출";
            case TRANSFER -> "이체";
        };
    }

    private String adjustmentType(AdjustmentType type) {
        return type == AdjustmentType.NORMAL ? "일반" : "환불";
    }

    private String scope(LedgerTransaction transaction) {
        if (transaction.getType() == TransactionType.TRANSFER) {
            return "";
        }
        return transaction.getScope() == TransactionScope.PERSONAL ? "개인" : "공동";
    }

    private String memberName(
            Long memberId,
            Map<Long, HouseholdMember> members,
            boolean included
    ) {
        if (!included || memberId == null) {
            return null;
        }
        return members.get(memberId).getUser().getDisplayName();
    }

    private String referenceName(Long categoryId, Map<Long, Category> categories) {
        return categoryId == null ? null : categories.get(categoryId).getName();
    }

    private String accountName(
            TransactionAccountEntry entry,
            Map<Long, Account> accounts
    ) {
        return entry == null ? null : accounts.get(entry.getAccountId()).getName();
    }

    private String text(String value) {
        return Rfc4180CsvWriter.protectSpreadsheetText(value);
    }

    private String nullableId(Long value) {
        return value == null ? "" : value.toString();
    }

    private TransactionAccountEntry entry(
            List<TransactionAccountEntry> entries,
            EntryRole role
    ) {
        return entries.stream()
                .filter(candidate -> candidate.getEntryRole() == role)
                .findFirst()
                .orElse(null);
    }

    private ApiException invalidEntrySet() {
        return new ApiException(
                HttpStatus.CONFLICT,
                ApiErrorCode.TRANSACTION_ENTRY_SET_INVALID
        );
    }
}
