package io.github.xxh3898.ourledger.household;

import io.github.xxh3898.ourledger.identity.User;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "household_members")
public class HouseholdMember {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "household_id", nullable = false)
    private Household household;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private HouseholdRole role;

    @Column(name = "joined_at", nullable = false)
    private Instant joinedAt;

    protected HouseholdMember() {
    }

    private HouseholdMember(Household household, User user, HouseholdRole role) {
        this.household = household;
        this.user = user;
        this.role = role;
    }

    public static HouseholdMember create(Household household, User user, HouseholdRole role) {
        if (household == null || user == null || role == null) {
            throw new IllegalArgumentException("HouseholdMember 필드는 필수입니다.");
        }
        return new HouseholdMember(household, user, role);
    }

    @PrePersist
    void onCreate() {
        joinedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public Household getHousehold() {
        return household;
    }

    public User getUser() {
        return user;
    }

    public HouseholdRole getRole() {
        return role;
    }

    public Instant getJoinedAt() {
        return joinedAt;
    }
}
