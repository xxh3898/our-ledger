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
@Table(name = "categories")
public class Category {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "household_id", nullable = false)
    private Long householdId;

    @Column(name = "group_id")
    private Long groupId;

    @Column(nullable = false, length = 100)
    private String name;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private CategoryType type;

    @Column(name = "icon_key", length = 64)
    private String iconKey;

    @Column(name = "color_key", length = 64)
    private String colorKey;

    @Column(name = "sort_order", nullable = false)
    private int sortOrder;

    @Column(name = "archived_at")
    private Instant archivedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Category() {
    }

    private Category(
            Long householdId,
            Long groupId,
            String name,
            CategoryType type,
            String iconKey,
            String colorKey,
            int sortOrder
    ) {
        this.householdId = householdId;
        this.type = type;
        apply(groupId, name, iconKey, colorKey, sortOrder);
    }

    public static Category create(
            Long householdId,
            Long groupId,
            String name,
            CategoryType type,
            String iconKey,
            String colorKey,
            int sortOrder
    ) {
        return new Category(
                householdId,
                groupId,
                name,
                type,
                iconKey,
                colorKey,
                sortOrder
        );
    }

    public void update(
            Long groupId,
            String name,
            String iconKey,
            String colorKey,
            int sortOrder,
            boolean archived
    ) {
        apply(groupId, name, iconKey, colorKey, sortOrder);
        if (archived && archivedAt == null) {
            archivedAt = Instant.now();
        } else if (!archived) {
            archivedAt = null;
        }
    }

    private void apply(
            Long groupId,
            String name,
            String iconKey,
            String colorKey,
            int sortOrder
    ) {
        this.groupId = groupId;
        this.name = name.strip();
        this.iconKey = stripToNull(iconKey);
        this.colorKey = stripToNull(colorKey);
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

    public Long getGroupId() {
        return groupId;
    }

    public String getName() {
        return name;
    }

    public CategoryType getType() {
        return type;
    }

    public String getIconKey() {
        return iconKey;
    }

    public String getColorKey() {
        return colorKey;
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
