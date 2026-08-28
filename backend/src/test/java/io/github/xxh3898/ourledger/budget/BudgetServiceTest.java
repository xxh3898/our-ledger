package io.github.xxh3898.ourledger.budget;

import io.github.xxh3898.ourledger.api.ApiErrorCode;
import io.github.xxh3898.ourledger.api.ApiException;
import io.github.xxh3898.ourledger.category.CategoryService;
import io.github.xxh3898.ourledger.household.HouseholdMemberResolver;
import io.github.xxh3898.ourledger.household.HouseholdQueryService;
import io.github.xxh3898.ourledger.security.CurrentHousehold;
import io.github.xxh3898.ourledger.transaction.LedgerTransactionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.YearMonth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class BudgetServiceTest {

    @Test
    void should_mapBudgetDuplicate_when_databaseUniqueRaceOccurs() {
        BudgetRepository budgetRepository = mock(BudgetRepository.class);
        when(budgetRepository.existsIdentity(
                anyLong(), any(), any(), isNull(), isNull(), isNull()))
                .thenReturn(false);
        when(budgetRepository.saveAndFlush(any(Budget.class)))
                .thenThrow(new DataIntegrityViolationException(
                        "duplicate",
                        new IllegalStateException("constraint uq_budgets_identity")
                ));
        BudgetService service = new BudgetService(
                budgetRepository,
                mock(LedgerTransactionRepository.class),
                mock(HouseholdMemberResolver.class),
                mock(HouseholdQueryService.class),
                mock(CategoryService.class)
        );
        CurrentHousehold currentHousehold = new CurrentHousehold(
                1L,
                "owner@example.test",
                "Owner",
                10L,
                "Household",
                "KRW",
                "Asia/Seoul",
                null
        );

        assertThatThrownBy(() -> service.create(
                currentHousehold,
                new BudgetCreateRequest(
                        YearMonth.of(2026, 8),
                        BudgetScope.HOUSEHOLD,
                        null,
                        null,
                        100_000L
                )
        )).isInstanceOfSatisfying(ApiException.class, exception ->
                assertThat(exception.code()).isEqualTo(ApiErrorCode.BUDGET_DUPLICATE));
    }
}
