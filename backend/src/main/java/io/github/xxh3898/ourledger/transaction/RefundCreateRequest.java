package io.github.xxh3898.ourledger.transaction;

import java.time.Instant;

public record RefundCreateRequest(
        Long amount,
        Instant occurredAt,
        String memo
) {
}
