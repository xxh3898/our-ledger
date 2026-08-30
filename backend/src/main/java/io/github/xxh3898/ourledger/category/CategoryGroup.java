package io.github.xxh3898.ourledger.category;

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

@Entity
@Table(name = "category_groups")
public class CategoryGroup {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private CategoryType type;

    @Column(name = "sort_order", nullable = false)
    private int sortOrder;

    @Column(name = "archived_at")
    private Instant archivedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected CategoryGroup() {
    }

    private CategoryGroup(Long householdId, String name, CategoryType type, int sortOrder) {
        this.householdId = householdId;
        this.name = name.strip();
        this.type = type;
        this.sortOrder = sortOrder;
    }

    public static CategoryGroup create(
            Long householdId,
            String name,
            CategoryType type,
            int sortOrder
    ) {
        return new CategoryGroup(householdId, name, type, sortOrder);
    }

    public void update(String name, int sortOrder, boolean archived) {
        this.name = name.strip();
        this.sortOrder = sortOrder;
        if (archived && archivedAt == null) {
            archivedAt = Instant.now();
        } else if (!archived) {
            archivedAt = null;
        }
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

    public String getName() {
        return name;
    }

    public CategoryType getType() {
        return type;
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
