package io.github.xxh3898.ourledger.recurring;

import io.github.xxh3898.ourledger.transaction.EntryRole;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "recurring_transaction_accounts")
public class RecurringTransactionAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(name = "recurring_transaction_id", nullable = false)
    private Long recurringTransactionId;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    @Enumerated(EnumType.STRING)
    @Column(name = "entry_role", nullable = false, length = 16)
    private EntryRole entryRole;

    protected RecurringTransactionAccount() {
    }

    private RecurringTransactionAccount(
            Long householdId,
            Long recurringTransactionId,
            Long accountId,
            EntryRole entryRole
    ) {
        this.householdId = householdId;
        this.recurringTransactionId = recurringTransactionId;
        this.accountId = accountId;
        this.entryRole = entryRole;
    }

    public static RecurringTransactionAccount create(
            Long householdId,
            Long recurringTransactionId,
            Long accountId,
            EntryRole entryRole
    ) {
        return new RecurringTransactionAccount(
                householdId, recurringTransactionId, accountId, entryRole);
    }

    public Long getId() { return id; }
    public Long getHouseholdId() { return householdId; }
    public Long getRecurringTransactionId() { return recurringTransactionId; }
    public Long getAccountId() { return accountId; }
    public EntryRole getEntryRole() { return entryRole; }
}
