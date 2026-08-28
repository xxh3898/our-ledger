package io.github.xxh3898.ourledger.transaction;

public final class NetSpendingCalculator {

    private NetSpendingCalculator() {
    }

    public static long amountOf(LedgerTransaction transaction) {
        if (transaction.getType() != TransactionType.EXPENSE) {
            return 0;
        }
        if (transaction.getAdjustmentType() == AdjustmentType.REFUND) {
            return Math.negateExact(transaction.getAmount());
        }
        return transaction.getAmount();
    }
}
