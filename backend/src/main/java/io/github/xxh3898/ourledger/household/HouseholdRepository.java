package io.github.xxh3898.ourledger.household;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface HouseholdRepository extends JpaRepository<Household, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select household from Household household where household.id = :id")
    Optional<Household> findByIdForUpdate(@Param("id") Long id);
}
