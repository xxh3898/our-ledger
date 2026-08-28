package io.github.xxh3898.ourledger.goal;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.YearMonth;

public final class GoalProjectionCalculator {

    private static final BigDecimal ONE_HUNDRED = BigDecimal.valueOf(100);

    private GoalProjectionCalculator() {
    }

    public static Projection calculate(
            long currentAmount,
            long targetAmount,
            Long recentAverageMonthlySavingsAmount,
            YearMonth currentMonth
    ) {
        long remainingAmount = Math.max(
                Math.subtractExact(targetAmount, currentAmount),
                0
        );
        BigDecimal achievementRate = BigDecimal.valueOf(currentAmount)
                .multiply(ONE_HUNDRED)
                .divide(BigDecimal.valueOf(targetAmount), 1, RoundingMode.HALF_UP);
        if (remainingAmount == 0) {
            return new Projection(
                    achievementRate,
                    remainingAmount,
                    GoalProjectionStatus.ACHIEVED,
                    null
            );
        }
        if (recentAverageMonthlySavingsAmount == null) {
            return new Projection(
                    achievementRate,
                    remainingAmount,
                    GoalProjectionStatus.INSUFFICIENT_HISTORY,
                    null
            );
        }
        if (recentAverageMonthlySavingsAmount <= 0) {
            return new Projection(
                    achievementRate,
                    remainingAmount,
                    GoalProjectionStatus.NON_POSITIVE_AVERAGE,
                    null
            );
        }
        long months = BigDecimal.valueOf(remainingAmount)
                .divide(
                        BigDecimal.valueOf(recentAverageMonthlySavingsAmount),
                        0,
                        RoundingMode.CEILING
                )
                .longValueExact();
        return new Projection(
                achievementRate,
                remainingAmount,
                GoalProjectionStatus.PROJECTED,
                currentMonth.plusMonths(months)
        );
    }

    public record Projection(
            BigDecimal achievementRate,
            long remainingAmount,
            GoalProjectionStatus status,
            YearMonth expectedAchievementMonth
    ) {
    }
}
