---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-001: Household 기반 데이터 경계

## Status

Accepted

## Context

두 사용자가 같은 데이터를 공유하지만 다른 Household 데이터와 섞여서는 안 된다. 단일 사용자 전용 FK 구조는 향후 권한 검증과 테스트를 어렵게 한다.

## Decision

모든 재무 데이터의 tenant boundary를 `Household`로 정한다. User는 HouseholdMember로 연결하고, Account·Category·Transaction·Budget·RecurringTransaction·Goal은 Household를 직접 참조한다. 주요 FK는 Household 일치를 DB와 서비스에서 함께 검증한다.

## Consequences

### 장점

- IDOR와 교차 Household 참조 방어
- 조회 조건과 권한 정책 일관성
- 향후 Household 확장 가능

### 비용과 위험

- 복합 FK와 query 조건 증가
- 모든 Repository에서 Household 조건 누락 여부를 점검해야 함

## Rejected Alternatives

### User ID만 직접 저장

공동 데이터 소유권과 두 사용자 권한을 중복 모델링하게 되어 거절한다.
