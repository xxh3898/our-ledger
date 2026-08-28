package io.github.xxh3898.ourledger.goal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.time.Instant;

@Entity
@Table(name = "goals")
public class Goal {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private GoalType type;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(name = "target_amount", nullable = false)
    private long targetAmount;

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

    protected Goal() {
    }

    private Goal(
            Long householdId,
            GoalType type,
            String name,
            long targetAmount,
            Long actorMemberId,
            Instant now
    ) {
        this.householdId = householdId;
        this.type = type;
        this.name = name.strip();
        this.targetAmount = targetAmount;
        this.createdAt = now;
        this.createdBy = actorMemberId;
        this.updatedAt = now;
        this.updatedBy = actorMemberId;
    }

    public static Goal createMarriage(
            Long householdId,
            String name,
            long targetAmount,
            Long actorMemberId,
            Instant now
    ) {
        return new Goal(
                householdId,
                GoalType.MARRIAGE,
                name,
                targetAmount,
                actorMemberId,
                now
        );
    }

    public void update(
            String name,
            long targetAmount,
            Long actorMemberId,
            Instant now
    ) {
        this.name = name.strip();
        this.targetAmount = targetAmount;
        this.updatedAt = now;
        this.updatedBy = actorMemberId;
    }

    public Long getId() {
        return id;
    }

    public Long getHouseholdId() {
        return householdId;
    }

    public GoalType getType() {
        return type;
    }

    public String getName() {
        return name;
    }

    public long getTargetAmount() {
        return targetAmount;
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
}
