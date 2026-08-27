---
status: active
version: 0.4
last_updated: 2026-08-28
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
- `TRANSACTION_ENTRY_SET_INVALID`
- `TRANSACTION_REFUND_ORIGINAL_REQUIRED`
- `TRANSACTION_REFUND_EXCEEDS_ORIGINAL`
- `TRANSFER_SAME_ACCOUNT_NOT_ALLOWED`
- `CATEGORY_TYPE_MISMATCH`
- `BUDGET_DUPLICATE`
- `RECURRING_OCCURRENCE_ALREADY_CREATED`
- `GOAL_ACCOUNT_ALREADY_ASSIGNED`

### Ledger code

- `INVALID_REQUEST`: JSON, enum/date/query 형식과 필수·크기·숫자 범위 validation 실패 (`400`)
- `RESOURCE_NOT_FOUND`: current Household에서 Member/Account/Category/Transaction을 찾을 수 없음 (`404`)
- `RESOURCE_STATE_CONFLICT`: DB unique/state race 등 현재 상태 충돌 (`409`)
- `CATEGORY_NAME_CONFLICT`: 같은 Household/type의 active Category 이름 중복 (`409`)
- `CATEGORY_GROUP_TYPE_MISMATCH`: Category와 Group type 불일치 (`422`)
- `ARCHIVED_CATEGORY_GROUP_NOT_ALLOWED`: 보관 Group으로 Category 생성·이동 (`422`)
- `CATEGORY_TYPE_MISMATCH`: Transaction과 Category type 불일치 (`422`)
- `ARCHIVED_ACCOUNT_NOT_ALLOWED`, `ARCHIVED_CATEGORY_NOT_ALLOWED`: 보관 기준정보의 신규 posting (`422`)
- `TRANSACTION_INVALID_SCOPE`: PERSONAL/SHARED owner 조합 또는 INCOME payer 규칙 위반 (`422`)
- `TRANSACTION_VERSION_CONFLICT`: stale PATCH/DELETE version (`409`)
- `TRANSACTION_ENTRY_SET_INVALID`: 저장된 거래의 role/delta/Account Entry exact set 불일치 (`409`)
- `TRANSFER_SAME_ACCOUNT_NOT_ALLOWED`: source와 destination 동일 (`422`)
- `UNSUPPORTED_TRANSFER_SOURCE`: LIABILITY source 이체 (`422`)
- `CREDIT_CARD_NATURE_REQUIRED`: CREDIT_CARD/ASSET 조합 (`422`)
- `UNSUPPORTED_ADJUSTMENT_TYPE`: REFUND/reversal 요청 (`422`)
- `UNSUPPORTED_ACCOUNT_POSTING`: Transaction 유형과 Account nature/type 조합 불일치 (`422`)

## 보안

다른 Household의 리소스가 실제로 존재하는지 구분할 수 없도록 404 또는 일반화된 403 정책을 일관되게 적용한다. stack trace와 SQL을 응답하지 않는다.

Ledger의 ID로 지정된 Member/Account/Category/Transaction은 미존재와 cross-household를 모두 `404 RESOURCE_NOT_FOUND`로 처리한다. 목록 filter는 current Household query 경계 안에서만 평가하며 다른 Household 데이터를 반환하지 않는다.

- Access JWT가 없거나 signature/issuer/audience/time/email 검증에 실패하면 `401 AUTHENTICATION_REQUIRED`다.
- JWT가 유효하지만 내부 User가 없으면 `403 USER_NOT_REGISTERED`, 비활성이면 `403 USER_DISABLED`다.
- ACTIVE User에게 current membership이 없으면 `403 HOUSEHOLD_MEMBERSHIP_REQUIRED`, 둘 이상이면 `403 HOUSEHOLD_MEMBERSHIP_AMBIGUOUS`다.
- unsafe request의 CSRF token이 없거나 다르면 `403 CSRF_TOKEN_INVALID`다.
