---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 07-quality/financial-invariants.md
  - AGENTS.md
---

# 테스트 전략

## Backend

### 단위 테스트

- Transaction 생성 규칙
- Entry delta 계산
- 환불 가능액
- 저축액과 지표 공식
- 반복 날짜 계산
- Goal 예상일

### 통합 테스트

PostgreSQL Testcontainers를 사용한다.

- Flyway 전체 적용
- CHECK, unique, composite FK
- JPA mapping
- Household 격리
- 동시 수정 version 충돌
- 반복 생성 idempotency

### API 테스트

- 인증·CSRF
- validation과 error code
- filter 조합
- 삭제 후 계산 제외

## Frontend

- 금액·날짜·필터 변환 단위 테스트
- 빠른 입력 form 컴포넌트 테스트
- 달력·예산·자산 상태 테스트
- 핵심 사용자 흐름 E2E
- 모바일 viewport 접근성

## 계약 테스트

OpenAPI 또는 REST Docs 중 하나를 bootstrap 단계에서 선택해 API 구현과 문서를 동기화한다. 사람이 작성한 도메인 문서를 API 스키마로 대체하지 않는다.

## 회귀 우선순위

1. 재무 불변식
2. Household 경계
3. migration
4. 인증·인가
5. 핵심 입력·조회 흐름
6. 표현·디자인

## CI

`./scripts/verify.sh`가 단일 진입점이다. Pull Request required check에서 backend, frontend, docs, repository hygiene를 검증한다.
