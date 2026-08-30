package io.github.xxh3898.ourledger.account;

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

import java.time.Instant;
import java.time.LocalDate;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(length = 100)
    private String institution;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private AccountType type;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private AccountNature nature;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private AccountOwnership ownership;

    @Column(name = "owner_member_id")
    private Long ownerMemberId;

    @Column(name = "opening_balance", nullable = false)
    private long openingBalance;

    @Column(name = "opening_balance_as_of", nullable = false)
    private LocalDate openingBalanceAsOf;

    @Column(nullable = false, length = 3)
    private String currency;

    @Column(name = "last_four", length = 4)
    private String lastFour;

    @Column(name = "savings_enabled", nullable = false)
    private boolean savingsEnabled;

    @Column(name = "sort_order", nullable = false)
    private int sortOrder;

    @Column(name = "archived_at")
    private Instant archivedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Account() {
    }

    private Account(
            Long householdId,
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            String currency,
            String lastFour,
            boolean savingsEnabled,
            int sortOrder
    ) {
        this.householdId = householdId;
        apply(
                name,
                institution,
                type,
                nature,
                ownership,
                ownerMemberId,
                openingBalance,
                openingBalanceAsOf,
                currency,
                lastFour,
                savingsEnabled,
                sortOrder
        );
    }

    public static Account create(
            Long householdId,
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            String currency,
            String lastFour,
            boolean savingsEnabled,
            int sortOrder
    ) {
        return new Account(
                householdId,
                name,
                institution,
                type,
                nature,
                ownership,
                ownerMemberId,
                openingBalance,
                openingBalanceAsOf,
                currency,
                lastFour,
                savingsEnabled,
                sortOrder
        );
    }

    public void update(
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            String currency,
            String lastFour,
            boolean savingsEnabled,
            int sortOrder,
            boolean archived
    ) {
        apply(
                name,
                institution,
                type,
                nature,
                ownership,
                ownerMemberId,
                openingBalance,
                openingBalanceAsOf,
                currency,
                lastFour,
                savingsEnabled,
                sortOrder
        );
        if (archived && archivedAt == null) {
            archivedAt = Instant.now();
        } else if (!archived) {
            archivedAt = null;
        }
    }

    private void apply(
            String name,
            String institution,
            AccountType type,
            AccountNature nature,
            AccountOwnership ownership,
            Long ownerMemberId,
            long openingBalance,
            LocalDate openingBalanceAsOf,
            String currency,
            String lastFour,
            boolean savingsEnabled,
            int sortOrder
    ) {
        this.name = name.strip();
        this.institution = stripToNull(institution);
        this.type = type;
        this.nature = nature;
        this.ownership = ownership;
        this.ownerMemberId = ownerMemberId;
        this.openingBalance = openingBalance;
        this.openingBalanceAsOf = openingBalanceAsOf;
        this.currency = currency;
        this.lastFour = stripToNull(lastFour);
        this.savingsEnabled = savingsEnabled;
        this.sortOrder = sortOrder;
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

    public String getName() {
        return name;
    }

    public String getInstitution() {
        return institution;
    }

    public AccountType getType() {
        return type;
    }

    public AccountNature getNature() {
        return nature;
    }

    public AccountOwnership getOwnership() {
        return ownership;
    }

    public Long getOwnerMemberId() {
        return ownerMemberId;
    }

    public long getOpeningBalance() {
        return openingBalance;
    }

    public LocalDate getOpeningBalanceAsOf() {
        return openingBalanceAsOf;
    }

    public String getCurrency() {
        return currency;
    }

    public String getLastFour() {
        return lastFour;
    }

    public boolean isSavingsEnabled() {
        return savingsEnabled;
    }

    public int getSortOrder() {
        return sortOrder;
    }

    public Instant getArchivedAt() {
        return archivedAt;
    }

    public boolean isArchived() {
        return archivedAt != null;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
