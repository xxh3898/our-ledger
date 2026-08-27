---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - 04-api/error-contract.md
  - ADR-007
---

# API 규칙

## 기본

- prefix: `/api/v1`
- content type: `application/json`
- 날짜: `YYYY-MM-DD`
- 시각: ISO 8601 offset 포함
- 금액: JSON 정수
- ID: JSON number 또는 문자열 변환 정책을 frontend와 일관되게 유지

`/actuator/health`는 업무 API가 아니라 container와 CI가 사용하는 management endpoint이므로 `/api/v1` prefix의 예외다. Foundation에서는 `health`만 노출하고 detail과 다른 actuator endpoint는 공개하지 않는다.

## 주요 리소스

```text
/api/v1/auth
/api/v1/me
/api/v1/households/current
/api/v1/accounts
/api/v1/category-groups
/api/v1/categories
/api/v1/transactions
/api/v1/budgets
/api/v1/recurring-transactions
/api/v1/goals
/api/v1/statistics
/api/v1/assets
/api/v1/exports
```

## 응답

성공 응답을 불필요한 `success/data` envelope로 감싸지 않는다. 생성은 `201 Created`, 조회·수정은 `200 OK`, 삭제는 `204 No Content`를 기본으로 한다.

## 세션과 CSRF

Cookie 기반 인증을 사용하므로 상태 변경 요청은 CSRF 보호를 적용한다. frontend는 credential을 포함하고 CSRF 계약을 따른다.

## 동시 수정

Transaction 등 충돌 가능 리소스는 version을 요청에 포함한다. 오래된 version이면 `409 Conflict`와 명시적 오류 코드를 반환한다.

## 멱등성

- 반복거래 생성은 DB unique로 보장
- 일반 POST의 idempotency key는 V1 기본 요구가 아님
- CSV export 같은 장시간 작업은 V1 데이터 규모에서는 동기 응답 가능

## 검증

field validation과 도메인 validation을 구분한다. HTTP status만으로 원인을 표현하지 않고 안정적인 error code를 제공한다.

API 계약 문서화 도구는 Spring REST Docs를 사용한다. request/response test가 생성한 snippet을 canonical API 문서에 조립하며, test를 통과하지 않은 hand-written response 예시만으로 구현 완료를 주장하지 않는다.
