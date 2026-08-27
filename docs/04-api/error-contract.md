---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - 06-security/authorization.md
---

# 오류 계약

## 형식

```json
{
  "code": "TRANSACTION_REFUND_EXCEEDS_ORIGINAL",
  "message": "환불 가능 금액을 초과했습니다.",
  "fieldErrors": [
    {
      "field": "amount",
      "code": "exceedsRemainingRefundableAmount",
      "message": "남은 환불 가능 금액 이하로 입력해야 합니다."
    }
  ],
  "traceId": "선택적 추적 식별자"
}
```

`message`는 사용자 표시 가능 문구지만 frontend가 비즈니스 분기를 message 문자열에 의존하지 않는다.

## HTTP status

| 상태 | 사용 |
|---:|---|
| 400 | JSON 형식, query 조합 등 잘못된 요청 |
| 401 | 미인증 |
| 403 | 인증됐지만 Household 권한 없음 또는 CSRF 실패 |
| 404 | 현재 Household에서 리소스를 찾을 수 없음 |
| 409 | version 충돌, 중복 생성, 상태 충돌 |
| 422 | 문법은 유효하나 도메인 규칙 위반 |
| 500 | 예상하지 못한 서버 오류 |

## 주요 코드

- `AUTHENTICATION_REQUIRED`
- `ACCESS_DENIED`
- `USER_NOT_REGISTERED`
- `USER_DISABLED`
- `HOUSEHOLD_MEMBERSHIP_REQUIRED`
- `HOUSEHOLD_MEMBERSHIP_AMBIGUOUS`
- `CSRF_TOKEN_INVALID`
- `HOUSEHOLD_MEMBER_LIMIT_REACHED`
- `RESOURCE_NOT_FOUND`
- `TRANSACTION_VERSION_CONFLICT`
- `TRANSACTION_INVALID_SCOPE`
- `TRANSACTION_INVALID_ACCOUNT_ENTRY`
- `TRANSACTION_REFUND_ORIGINAL_REQUIRED`
- `TRANSACTION_REFUND_EXCEEDS_ORIGINAL`
- `TRANSFER_SAME_ACCOUNT_NOT_ALLOWED`
- `CATEGORY_TYPE_MISMATCH`
- `BUDGET_DUPLICATE`
- `RECURRING_OCCURRENCE_ALREADY_CREATED`
- `GOAL_ACCOUNT_ALREADY_ASSIGNED`

## 보안

다른 Household의 리소스가 실제로 존재하는지 구분할 수 없도록 404 또는 일반화된 403 정책을 일관되게 적용한다. stack trace와 SQL을 응답하지 않는다.

- Access JWT가 없거나 signature/issuer/audience/time/email 검증에 실패하면 `401 AUTHENTICATION_REQUIRED`다.
- JWT가 유효하지만 내부 User가 없으면 `403 USER_NOT_REGISTERED`, 비활성이면 `403 USER_DISABLED`다.
- ACTIVE User에게 current membership이 없으면 `403 HOUSEHOLD_MEMBERSHIP_REQUIRED`, 둘 이상이면 `403 HOUSEHOLD_MEMBERSHIP_AMBIGUOUS`다.
- unsafe request의 CSRF token이 없거나 다르면 `403 CSRF_TOKEN_INVALID`다.
