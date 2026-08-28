package io.github.xxh3898.ourledger.goal;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class GoalAccountId implements Serializable {

    @Column(name = "goal_id", nullable = false)
    private Long goalId;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    protected GoalAccountId() {
    }

    public GoalAccountId(Long goalId, Long accountId) {
        this.goalId = goalId;
        this.accountId = accountId;
    }

    public Long getGoalId() {
        return goalId;
    }

    public Long getAccountId() {
        return accountId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof GoalAccountId that)) {
            return false;
        }
        return Objects.equals(goalId, that.goalId)
                && Objects.equals(accountId, that.accountId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(goalId, accountId);
    }
}
