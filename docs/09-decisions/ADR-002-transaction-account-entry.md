---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-002: Transaction과 Account Entry 분리

## Status

Accepted

## Context

단순 source/destination 컬럼만으로는 신용카드 사용, 카드대금 납부, 환불, 잔액 변화를 일관되게 표현하기 어렵다.

## Decision

`transactions`는 경제 사건을, `transaction_account_entries`는 Account 잔액 변화를 표현한다. Transaction과 Entry는 하나의 DB transaction으로 저장한다.

## Consequences

### 장점

- ASSET과 LIABILITY를 같은 구조로 계산
- 카드대금 중복 소비 방지
- 잔액 공식 단순화

### 비용과 위험

- 거래별 Entry 수와 delta 규칙 테스트 필요
- 완전한 복식부기가 아니므로 임의 확장 시 회계 의미를 재검토해야 함

## Rejected Alternatives

### Transaction에 source_account_id와 destination_account_id만 저장

일반 지출과 신용카드 부채 방향 처리가 분기투성이가 되어 거절한다.
