---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-006: Goal은 실제 Account와 연결

## Status

Accepted

## Context

결혼자금을 거래 이체와 Goal 기여금에 각각 입력하면 이중 입력과 금액 불일치가 발생한다.

## Decision

Goal은 `goal_accounts`로 실제 Account를 연결한다. 현재 보유금과 누적 저축은 Transaction/Entry에서 계산하고 별도 기여금 입력 기능을 만들지 않는다. 하나의 Account는 하나의 Goal에만 연결한다.

## Consequences

- Goal과 실제 자산 일치
- 중복 입력 제거
- Goal 계산이 Account history에 의존하므로 과거 수정 영향 테스트 필요

## Rejected Alternatives

### GoalContribution 별도 수동 입력

원장과 목표 잔액이 쉽게 어긋나므로 거절한다.
