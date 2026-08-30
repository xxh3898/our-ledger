package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.transaction.TransactionScope;
import io.github.xxh3898.ourledger.transaction.TransactionType;
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
import java.time.LocalDate;
import java.time.LocalTime;

@Entity
@Table(name = "recurring_transactions")
public class RecurringTransaction {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(nullable = false, length = 100)
    private String name;

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

    @Column(length = 500)
    private String memo;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private RecurrenceFrequency frequency;

    @Column(name = "interval_value", nullable = false)
    private int intervalValue;

    @Column(name = "start_date", nullable = false)
    private LocalDate startDate;

    @Column(name = "end_date")
    private LocalDate endDate;

    @Column(name = "scheduled_local_time", nullable = false)
    private LocalTime scheduledLocalTime;

    @Column(name = "auto_post", nullable = false)
    private boolean autoPost;

    @Column(nullable = false)
    private boolean active;

    @Column(name = "next_recurrence_date")
    private LocalDate nextRecurrenceDate;

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

    protected RecurringTransaction() {
    }

    private RecurringTransaction(
            Long householdId,
            String name,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            String memo,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            LocalTime scheduledLocalTime,
            boolean autoPost,
            boolean active,
            LocalDate nextRecurrenceDate,
            Long actorMemberId
    ) {
        this.householdId = householdId;
        this.createdBy = actorMemberId;
        apply(
                name, type, amount, scope, ownerMemberId, payerMemberId, categoryId,
                memo, frequency, intervalValue, startDate, endDate, scheduledLocalTime,
                autoPost, active, nextRecurrenceDate, actorMemberId
        );
    }

    public static RecurringTransaction create(
            Long householdId,
            String name,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            String memo,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            LocalTime scheduledLocalTime,
            boolean autoPost,
            boolean active,
            LocalDate nextRecurrenceDate,
            Long actorMemberId
    ) {
        return new RecurringTransaction(
                householdId, name, type, amount, scope, ownerMemberId, payerMemberId,
                categoryId, memo, frequency, intervalValue, startDate, endDate,
                scheduledLocalTime, autoPost, active, nextRecurrenceDate, actorMemberId
        );
    }

    public void update(
            String name,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            String memo,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            LocalTime scheduledLocalTime,
            boolean autoPost,
            boolean active,
            LocalDate nextRecurrenceDate,
            Long actorMemberId
    ) {
        apply(
                name, type, amount, scope, ownerMemberId, payerMemberId, categoryId,
                memo, frequency, intervalValue, startDate, endDate, scheduledLocalTime,
                autoPost, active, nextRecurrenceDate, actorMemberId
        );
    }

    private void apply(
            String name,
            TransactionType type,
            long amount,
            TransactionScope scope,
            Long ownerMemberId,
            Long payerMemberId,
            Long categoryId,
            String memo,
            RecurrenceFrequency frequency,
            int intervalValue,
            LocalDate startDate,
            LocalDate endDate,
            LocalTime scheduledLocalTime,
            boolean autoPost,
            boolean active,
            LocalDate nextRecurrenceDate,
            Long actorMemberId
    ) {
        this.name = name.strip();
        this.type = type;
        this.amount = amount;
        this.scope = scope;
        this.ownerMemberId = ownerMemberId;
        this.payerMemberId = payerMemberId;
        this.categoryId = categoryId;
        this.memo = stripToNull(memo);
        this.frequency = frequency;
        this.intervalValue = intervalValue;
        this.startDate = startDate;
        this.endDate = endDate;
        this.scheduledLocalTime = scheduledLocalTime;
        this.autoPost = autoPost;
        this.active = active;
        this.nextRecurrenceDate = nextRecurrenceDate;
        this.updatedBy = actorMemberId;
    }

    public void advanceTo(LocalDate nextRecurrenceDate) {
        this.nextRecurrenceDate = nextRecurrenceDate;
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
        return value == null || value.isBlank() ? null : value.strip();
    }

    public Long getId() { return id; }
    public Long getHouseholdId() { return householdId; }
    public String getName() { return name; }
    public TransactionType getType() { return type; }
    public long getAmount() { return amount; }
    public TransactionScope getScope() { return scope; }
    public Long getOwnerMemberId() { return ownerMemberId; }
    public Long getPayerMemberId() { return payerMemberId; }
    public Long getCategoryId() { return categoryId; }
    public String getMemo() { return memo; }
    public RecurrenceFrequency getFrequency() { return frequency; }
    public int getIntervalValue() { return intervalValue; }
    public LocalDate getStartDate() { return startDate; }
    public LocalDate getEndDate() { return endDate; }
    public LocalTime getScheduledLocalTime() { return scheduledLocalTime; }
    public boolean isAutoPost() { return autoPost; }
    public boolean isActive() { return active; }
    public LocalDate getNextRecurrenceDate() { return nextRecurrenceDate; }
    public long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Long getCreatedBy() { return createdBy; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Long getUpdatedBy() { return updatedBy; }
}
