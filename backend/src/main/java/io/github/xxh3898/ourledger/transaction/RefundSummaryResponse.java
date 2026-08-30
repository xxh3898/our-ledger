package io.github.xxh3898.ourledger.transaction;

import java.time.Instant;
import java.util.List;

public record RefundSummaryResponse(
        Long originalTransactionId,
        long originalAmount,
        long refundedAmount,
        long remainingRefundableAmount,
        List<Refund> refunds
) {

    public RefundSummaryResponse {
        refunds = List.copyOf(refunds);
    }

    public record Refund(
            Long id,
            long amount,
            Instant occurredAt,
            String memo,
            long version
    ) {
    }
}
