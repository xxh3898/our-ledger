package io.github.xxh3898.ourledger.transaction;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;

@Entity
@Table(name = "transactions")
public class LedgerTransaction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private TransactionType type;

    @Column(nullable = false)
    private long amount;

    @Enumerated(EnumType.STRING)
    @Column(length = 16)
    private TransactionScope scope;

    @Column(name = "owner_member_id")
    private Long ownerMemberId;

    @Column(name = "payer_member_id")
    private Long payerMemberId;

    @Column(name = "category_id")
    private Long categoryId;

    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    @Column(length = 500)
    private String memo;

    @Enumerated(EnumType.STRING)
    @Column(name = "adjustment_type", nullable = false, length = 16)
    private AdjustmentType adjustmentType;

    @Column(name = "reverses_transaction_id")
    private Long reversesTransactionId;

    @Version
    @Column(nullable = false)
    private long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "created_by", nullable = false)
    private Long createdBy;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "updated_by", nullable = false)
    private Long updatedBy;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @Column(name = "deleted_by")
    private Long deletedBy;

    protected LedgerTransaction() {
    }

    private LedgerTransaction(
            Long householdId,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId,
            Long actorMemberId
    ) {
        this.householdId = householdId;
        this.createdBy = actorMemberId;
        apply(
                type,
                amount,
                scope,
                ownerMemberId,
                payerMemberId,
                categoryId,
                occurredAt,
                memo,
                adjustmentType,
                reversesTransactionId,
                actorMemberId
        );
    }

    public static LedgerTransaction create(
            Long householdId,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId,
            Long actorMemberId
    ) {
        return new LedgerTransaction(
                householdId,
                type,
                amount,
                scope,
                ownerMemberId,
                payerMemberId,
                categoryId,
                occurredAt,
                memo,
                adjustmentType,
                reversesTransactionId,
                actorMemberId
        );
    }

    public void update(
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId,
            Long actorMemberId
    ) {
        apply(
                type,
                amount,
                scope,
                ownerMemberId,
                payerMemberId,
                categoryId,
                occurredAt,
                memo,
                adjustmentType,
                reversesTransactionId,
                actorMemberId
        );
    }

    private void apply(
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            Instant occurredAt,
            String memo,
            AdjustmentType adjustmentType,
            Long reversesTransactionId,
            Long actorMemberId
    ) {
        this.type = type;
        this.amount = amount;
        this.scope = scope;
        this.ownerMemberId = ownerMemberId;
        this.payerMemberId = payerMemberId;
        this.categoryId = categoryId;
        this.occurredAt = occurredAt;
        this.memo = stripToNull(memo);
        this.adjustmentType = adjustmentType;
        this.reversesTransactionId = reversesTransactionId;
        this.updatedBy = actorMemberId;
    }

    public void delete(Long actorMemberId) {
        deletedAt = Instant.now();
        deletedBy = actorMemberId;
        updatedBy = actorMemberId;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }

    private static String stripToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.strip();
    }

    public Long getId() {
        return id;
    }

    public Long getHouseholdId() {
        return householdId;
    }

    public TransactionType getType() {
        return type;
    }

    public long getAmount() {
        return amount;
    }

    public TransactionScope getScope() {
        return scope;
    }

    public Long getOwnerMemberId() {
        return ownerMemberId;
    }

    public Long getPayerMemberId() {
        return payerMemberId;
    }

    public Long getCategoryId() {
        return categoryId;
    }

    public Instant getOccurredAt() {
        return occurredAt;
    }

    public String getMemo() {
        return memo;
    }

    public AdjustmentType getAdjustmentType() {
        return adjustmentType;
    }

    public Long getReversesTransactionId() {
        return reversesTransactionId;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Long getCreatedBy() {
        return createdBy;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public Long getUpdatedBy() {
        return updatedBy;
    }

    public Instant getDeletedAt() {
        return deletedAt;
    }

    public Long getDeletedBy() {
        return deletedBy;
    }
}
