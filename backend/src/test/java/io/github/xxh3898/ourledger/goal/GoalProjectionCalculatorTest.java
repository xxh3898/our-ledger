package io.github.xxh3898.ourledger.goal;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.YearMonth;

import static org.assertj.core.api.Assertions.assertThat;

class GoalProjectionCalculatorTest {

    private static final YearMonth AUGUST_2026 = YearMonth.of(2026, 8);

    @Test
    void should_returnAchievedAndRawOverOneHundredRate_when_targetIsReached() {
        GoalProjectionCalculator.Projection projection = GoalProjectionCalculator.calculate(
                120_000_000,
                100_000_000,
                null,
                AUGUST_2026
        );

        assertThat(projection.achievementRate()).isEqualByComparingTo(new BigDecimal("120.0"));
        assertThat(projection.remainingAmount()).isZero();
        assertThat(projection.status()).isEqualTo(GoalProjectionStatus.ACHIEVED);
        assertThat(projection.expectedAchievementMonth()).isNull();
    }

    @Test
    void should_distinguishMissingAndNonPositiveAverage_when_targetRemains() {
        assertThat(GoalProjectionCalculator.calculate(
                10_000, 100_000, null, AUGUST_2026).status())
                .isEqualTo(GoalProjectionStatus.INSUFFICIENT_HISTORY);
        assertThat(GoalProjectionCalculator.calculate(
                10_000, 100_000, 0L, AUGUST_2026).status())
                .isEqualTo(GoalProjectionStatus.NON_POSITIVE_AVERAGE);
        assertThat(GoalProjectionCalculator.calculate(
                10_000, 100_000, -1L, AUGUST_2026).status())
                .isEqualTo(GoalProjectionStatus.NON_POSITIVE_AVERAGE);
    }

    @Test
    void should_roundRateHalfUpAndProjectionMonthsUp_when_averageIsPositive() {
        GoalProjectionCalculator.Projection projection = GoalProjectionCalculator.calculate(
                10_000,
                100_000,
                40_000L,
                AUGUST_2026
        );

        assertThat(projection.achievementRate()).isEqualByComparingTo(new BigDecimal("10.0"));
        assertThat(projection.remainingAmount()).isEqualTo(90_000);
        assertThat(projection.status()).isEqualTo(GoalProjectionStatus.PROJECTED);
        assertThat(projection.expectedAchievementMonth()).isEqualTo(YearMonth.of(2026, 11));
    }

    @Test
    void should_keepNegativeCurrentAmountVisible_when_ledgerBalanceIsNegative() {
        GoalProjectionCalculator.Projection projection = GoalProjectionCalculator.calculate(
                -500,
                1_000,
                500L,
                AUGUST_2026
        );

        assertThat(projection.achievementRate()).isEqualByComparingTo(new BigDecimal("-50.0"));
        assertThat(projection.remainingAmount()).isEqualTo(1_500);
        assertThat(projection.expectedAchievementMonth()).isEqualTo(YearMonth.of(2026, 11));
    }
}
