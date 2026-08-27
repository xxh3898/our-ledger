---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-005: 반복규칙에서 실제 Transaction 생성

## Status

Accepted

## Context

통계 시점마다 반복규칙을 가상 거래로 해석하면 과거 확정값과 예정값이 섞이고 수정이 복잡해진다.

## Decision

RecurringTransaction은 일정 규칙만 저장하고 due date에 일반 Transaction과 Entry를 생성한다. `(generated_from_recurring_id, recurrence_date)`를 유일하게 해 중복을 막는다.

## Consequences

- 생성 뒤 일반 거래와 동일하게 조회·수정 가능
- 통계가 실제 Transaction만 보면 됨
- scheduler, 실패 재시도, 날짜 보정 테스트 필요

## Rejected Alternatives

### 조회 시 가상 거래 계산

잔액과 확정 여부가 불명확해져 거절한다.
