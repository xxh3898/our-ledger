package io.github.xxh3898.ourledger.goal;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "goal_accounts")
public class GoalAccount {

    @EmbeddedId
    private GoalAccountId id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(name = "starting_balance", nullable = false)
    private long startingBalance;

    @Column(name = "linked_at", nullable = false)
    private Instant linkedAt;

    @Column(name = "linked_by", nullable = false)
    private Long linkedBy;

    protected GoalAccount() {
    }

    private GoalAccount(
            Long goalId,
            Long accountId,
            Long householdId,
            long startingBalance,
            Instant linkedAt,
            Long linkedBy
    ) {
        this.id = new GoalAccountId(goalId, accountId);
        this.householdId = householdId;
        this.startingBalance = startingBalance;
        this.linkedAt = linkedAt;
        this.linkedBy = linkedBy;
    }

    public static GoalAccount link(
            Long goalId,
            Long accountId,
            Long householdId,
            long startingBalance,
            Instant linkedAt,
            Long linkedBy
    ) {
        return new GoalAccount(
                goalId,
                accountId,
                householdId,
                startingBalance,
                linkedAt,
                linkedBy
        );
    }

    public Long getGoalId() {
        return id.getGoalId();
    }

    public Long getAccountId() {
        return id.getAccountId();
    }

    public Long getHouseholdId() {
        return householdId;
    }

    public long getStartingBalance() {
        return startingBalance;
    }

    public Instant getLinkedAt() {
        return linkedAt;
    }

    public Long getLinkedBy() {
        return linkedBy;
    }
}
