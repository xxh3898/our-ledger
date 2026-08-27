---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-003: 개인·공동 Scope와 Owner·Payer 분리

## Status

Accepted

## Context

누가 돈을 결제했는지와 누구의 소비인지는 다를 수 있다. 로그인 사용자 기준 ME/PARTNER를 저장하면 데이터 의미가 조회자에 따라 변한다.

## Decision

INCOME과 EXPENSE에 `PERSONAL` 또는 `SHARED` Scope를 저장한다. PERSONAL에는 실제 `owner_member_id`를 저장한다. EXPENSE에는 실제 결제자를 나타내는 `payer_member_id`를 별도로 둘 수 있다.

## Consequences

- 개인·공동 필터가 안정적이다.
- 개인 카드 공동지출과 대리결제를 표현할 수 있다.
- Payer 기반 정산은 하지 않는다.

## Rejected Alternatives

### PERSONAL_ME / PERSONAL_PARTNER 저장

로그인 사용자마다 의미가 달라져 거절한다.
