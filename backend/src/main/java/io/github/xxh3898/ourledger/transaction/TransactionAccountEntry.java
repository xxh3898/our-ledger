package io.github.xxh3898.ourledger.transaction;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "transaction_account_entries")
public class TransactionAccountEntry {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(name = "transaction_id", nullable = false)
    private Long transactionId;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    @Enumerated(EnumType.STRING)
    @Column(name = "entry_role", nullable = false, length = 16)
    private EntryRole entryRole;

    @Column(name = "balance_delta", nullable = false)
    private long balanceDelta;

    protected TransactionAccountEntry() {
    }

    private TransactionAccountEntry(
            Long householdId,
            Long transactionId,
            Long accountId,
            EntryRole entryRole,
            long balanceDelta
    ) {
        this.householdId = householdId;
        this.transactionId = transactionId;
        this.accountId = accountId;
        this.entryRole = entryRole;
        this.balanceDelta = balanceDelta;
    }

    public static TransactionAccountEntry primary(
            Long householdId,
            Long transactionId,
            Long accountId,
            long balanceDelta
    ) {
        return new TransactionAccountEntry(
                householdId,
                transactionId,
                accountId,
                EntryRole.PRIMARY,
                balanceDelta
        );
    }

    public void updatePrimary(Long accountId, long balanceDelta) {
        this.accountId = accountId;
        this.entryRole = EntryRole.PRIMARY;
        this.balanceDelta = balanceDelta;
    }

    public Long getId() {
        return id;
    }

    public Long getHouseholdId() {
        return householdId;
    }

    public Long getTransactionId() {
        return transactionId;
    }

    public Long getAccountId() {
        return accountId;
    }

    public EntryRole getEntryRole() {
        return entryRole;
    }

    public long getBalanceDelta() {
        return balanceDelta;
    }
}
