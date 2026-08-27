package io.github.xxh3898.ourledger.transaction;

import jakarta.persistence.criteria.Subquery;
import org.springframework.data.jpa.domain.Specification;

import java.time.Instant;

final class TransactionSpecifications {

    private TransactionSpecifications() {
    }

    static Specification<LedgerTransaction> visibleTo(Long householdId) {
        return (root, query, criteriaBuilder) -> criteriaBuilder.and(
                criteriaBuilder.equal(root.get("householdId"), householdId),
                criteriaBuilder.isNull(root.get("deletedAt"))
        );
    }

    static Specification<LedgerTransaction> occurredAtOrAfter(Instant from) {
        return (root, query, criteriaBuilder) ->
                criteriaBuilder.greaterThanOrEqualTo(root.get("occurredAt"), from);
    }

    static Specification<LedgerTransaction> occurredBefore(Instant toExclusive) {
        return (root, query, criteriaBuilder) ->
                criteriaBuilder.lessThan(root.get("occurredAt"), toExclusive);
    }

    static Specification<LedgerTransaction> typeEquals(TransactionType type) {
        return (root, query, criteriaBuilder) -> criteriaBuilder.equal(root.get("type"), type);
    }

    static Specification<LedgerTransaction> scopeEquals(TransactionScope scope) {
        return (root, query, criteriaBuilder) -> criteriaBuilder.equal(root.get("scope"), scope);
    }

    static Specification<LedgerTransaction> ownerEquals(Long ownerMemberId) {
        return (root, query, criteriaBuilder) ->
                criteriaBuilder.equal(root.get("ownerMemberId"), ownerMemberId);
    }

    static Specification<LedgerTransaction> categoryEquals(Long categoryId) {
        return (root, query, criteriaBuilder) ->
                criteriaBuilder.equal(root.get("categoryId"), categoryId);
    }

    static Specification<LedgerTransaction> accountEquals(Long accountId) {
        return (root, query, criteriaBuilder) -> {
            Subquery<Long> entryQuery = query.subquery(Long.class);
            var entry = entryQuery.from(TransactionAccountEntry.class);
            entryQuery.select(entry.get("id"));
            entryQuery.where(
                    criteriaBuilder.equal(entry.get("transactionId"), root.get("id")),
                    criteriaBuilder.equal(entry.get("householdId"), root.get("householdId")),
                    criteriaBuilder.equal(entry.get("accountId"), accountId)
            );
            return criteriaBuilder.exists(entryQuery);
        };
    }
}
