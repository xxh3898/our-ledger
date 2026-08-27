---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - ADR-001
  - 06-security/authorization.md
---

# Household 도메인

## 역할

`Household`는 모든 재무 데이터의 tenant boundary다. User는 `HouseholdMember`를 통해 Household에 참여한다.

## V1 정책

- 하나의 Household에는 활성 Member가 최대 2명이다.
- 두 Member 모두 거래, 예산, Account, Category, Goal을 조회·관리할 수 있다.
- 역할은 `OWNER`, `MEMBER`를 둔다.
- 계정·비밀번호·세션 같은 본인 보안정보만 본인 범위다.
- 개인 소비는 상대 Member에게 비공개가 아니다.

## 불변 조건

- 모든 Account, Category, Transaction, Budget, RecurringTransaction, Goal은 하나의 Household에 속한다.
- 요청 사용자가 해당 Household의 활성 Member가 아니면 접근을 거부한다.
- 하위 엔티티 참조 시 ID뿐 아니라 Household 일치도 검증한다.
- 다른 Household의 ID 존재 여부가 오류 응답에서 노출되지 않게 한다.

## 삭제

V1에서 Household 자체 삭제 UI는 제공하지 않는다. 실제 운영 데이터 삭제는 백업과 복구 가능성을 확인한 별도 관리 절차로만 수행한다.
