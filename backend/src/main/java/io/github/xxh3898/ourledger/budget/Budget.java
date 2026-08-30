package io.github.xxh3898.ourledger.budget;

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

@Entity
@Table(name = "budgets")
public class Budget {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(name = "budget_month", nullable = false)
    private LocalDate budgetMonth;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private BudgetScope scope;

    @Column(name = "owner_member_id")
    private Long ownerMemberId;

    @Column(name = "category_id")
    private Long categoryId;

    @Column(nullable = false)
    private long amount;

    @Version
    @Column(nullable = false)
    private long version;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Budget() {
    }

    private Budget(
            Long householdId,
            LocalDate budgetMonth,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        this.householdId = householdId;
        apply(budgetMonth, scope, ownerMemberId, categoryId, amount);
    }

    public static Budget create(
            Long householdId,
            LocalDate budgetMonth,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        return new Budget(householdId, budgetMonth, scope, ownerMemberId, categoryId, amount);
    }

    public void update(
            LocalDate budgetMonth,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        apply(budgetMonth, scope, ownerMemberId, categoryId, amount);
    }

    private void apply(
            LocalDate budgetMonth,
            BudgetScope scope,
            Long ownerMemberId,
            Long categoryId,
            long amount
    ) {
        this.budgetMonth = budgetMonth;
        this.scope = scope;
        this.ownerMemberId = ownerMemberId;
        this.categoryId = categoryId;
        this.amount = amount;
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

    public Long getId() {
        return id;
    }

    public Long getHouseholdId() {
        return householdId;
    }

    public LocalDate getBudgetMonth() {
        return budgetMonth;
    }

    public BudgetScope getScope() {
        return scope;
    }

    public Long getOwnerMemberId() {
        return ownerMemberId;
    }

    public Long getCategoryId() {
        return categoryId;
    }

    public long getAmount() {
        return amount;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
