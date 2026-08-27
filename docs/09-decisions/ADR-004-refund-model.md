---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-004: 환불은 별도 REFUND Transaction

## Status

Accepted

## Context

음수 금액을 허용하면 일반 지출, 데이터 정정, 환불의 의미가 섞이고 Entry 방향 검증이 어려워진다.

## Decision

amount는 항상 양수다. 실제 환불은 `type=EXPENSE`, `adjustment_type=REFUND`, `reverses_transaction_id`를 가진 별도 Transaction으로 저장한다. 누적 환불은 원 거래액 이하로 제한한다.

## Consequences

- 전체·부분 환불 추적 가능
- 오입력 수정과 실제 환불 구분
- 통계는 NORMAL-REFUND로 계산

## Rejected Alternatives

### 음수 EXPENSE

원 거래 연결과 초과 환불 검증이 약해져 거절한다.
