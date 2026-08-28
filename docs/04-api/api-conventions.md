---
status: active
version: 0.6
last_updated: 2026-08-28
related:
  - 04-api/error-contract.md
  - ADR-008
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

애플리케이션 자체 로그인·로그아웃·비밀번호 API는 제공하지 않는다. `/api/v1/me`는 검증된 Access identity에 매핑된 내부 User와 현재 Household 정보를 반환한다.

### `GET /api/v1/me`

```json
{
  "userId": 1,
  "email": "owner@example.test",
  "displayName": "Owner",
  "householdId": 10,
  "householdName": "테스트 Household",
  "role": "OWNER"
}
```

### `GET /api/v1/households/current`

```json
{
  "householdId": 10,
  "name": "테스트 Household",
  "baseCurrency": "KRW",
  "timezone": "Asia/Seoul",
  "members": [
    {
      "memberId": 100,
      "userId": 1,
      "displayName": "Owner",
      "role": "OWNER"
    }
  ]
}
```

두 API의 ID는 server가 검증한 current Household principal에서만 나온다. 클라이언트가 query나 일반 header로 보낸 Household ID는 current 선택 또는 권한 근거가 아니다. 실제 response field는 `AuthHouseholdDocsTest`가 생성하는 `current-user`, `current-household` Spring REST Docs snippet으로 검증한다.

`members[]`는 `memberId`, `userId`, `displayName`, `role`을 반환한다. Ledger owner/payer 요청은 `memberId`를 사용한다.

## Basic Ledger API

모든 endpoint는 `CurrentHousehold.householdId`를 서버에서 적용하며 request body/query에 `householdId`를 받지 않는다. `PATCH`는 정의된 수정 필드를 전부 받는다. omitted/null 의미가 필요한 필드는 별도로 문서화한다.

### Account

```text
GET   /api/v1/accounts?includeArchived=false
POST  /api/v1/accounts
PATCH /api/v1/accounts/{accountId}
```

create/update는 `name`, nullable `institution`, `type`, `nature`, `ownership`, nullable `ownerMemberId`, `openingBalance`, `openingBalanceAsOf`, `currency`, nullable `lastFour`, `savingsEnabled`, `sortOrder`를 사용한다. update는 `archived` boolean을 추가로 요구한다. response는 해당 필드와 owner reference, `currentBalance`, `archived`, timestamp를 반환한다.

Entry가 연결된 Account의 update는 Account row를 잠그고 posting 분류 변경 여부를 검사한다. ASSET, CREDIT_CARD/LIABILITY, 기타 LIABILITY 사이를 바꿔 기존 Entry delta 의미를 변경하는 요청은 `409 ACCOUNT_POSTING_CLASSIFICATION_IMMUTABLE`로 거부한다. 동일 ASSET 분류 안의 type 변경과 이름·소유·보관 등 posting 분류에 영향을 주지 않는 수정은 유지한다.

### Category Group / Category

```text
GET   /api/v1/category-groups?includeArchived=false
POST  /api/v1/category-groups
PATCH /api/v1/category-groups/{groupId}
GET   /api/v1/categories?includeArchived=false
POST  /api/v1/categories
PATCH /api/v1/categories/{categoryId}
```

Group create는 `name`, `type`, `sortOrder`, update는 immutable type을 제외한 `name`, `sortOrder`, `archived`를 받는다. Category create는 nullable `groupId`, `name`, `type`, nullable `iconKey/colorKey`, `sortOrder`, update는 immutable type을 제외한 같은 편집 필드와 `archived`를 받는다.

active-only가 기본이며 `includeArchived=true`는 보관 row와 Group의 archive 상태를 반환한다. archived Group 소속 Category는 기본 선택 목록에서 제외한다.

### Transaction

```text
GET    /api/v1/transactions
GET    /api/v1/transactions/{transactionId}
POST   /api/v1/transactions
PATCH  /api/v1/transactions/{transactionId}
DELETE /api/v1/transactions/{transactionId}?version={version}
```

POST의 공통 필드는 `type`, positive `amount`, ISO 8601 `occurredAt`, nullable `memo`, `adjustmentType=NORMAL`, nullable `reversesTransactionId=null`이다. INCOME/EXPENSE는 `scope`, nullable `ownerMemberId/payerMemberId`, `categoryId`, `accountId`를 사용하고 source/destination은 null이다. TRANSFER는 scope/owner/payer/category/account가 null이고 `sourceAccountId`, `destinationAccountId`가 필수다. PATCH는 같은 필드와 현재 `version`을 요구한다.

response는 nullable owner/payer/Category, `version`, canonical `entries[]`를 포함한다. 각 Entry는 `id`, `role`, `balanceDelta`, Account reference를 제공하며 최상위 단일 `account`/`entry`는 제공하지 않는다. DELETE는 Transaction을 논리삭제하고 `204` 본문 없음으로 응답한다.

목록은 `occurred_at DESC, id DESC`로 정렬하고 다음 optional query를 고정한다.

| query | 의미 |
|---|---|
| `from`, `to` | Household timezone 기준 포함 날짜 `YYYY-MM-DD` |
| `type` | `INCOME`, `EXPENSE`, `TRANSFER` |
| `scope` | `PERSONAL` 또는 `SHARED` |
| `ownerMemberId` | PERSONAL owner Member ID |
| `categoryId` | Category ID |
| `accountId` | PRIMARY/SOURCE/DESTINATION 중 일치하는 Entry Account ID |

`from > to`는 `400 INVALID_REQUEST`다. 논리삭제 Transaction은 목록과 detail에서 제외한다. 실제 request/response는 `LedgerApiDocsTest`가 생성하는 `ledger-account-*`, `ledger-category-*`, `ledger-transaction-*`, `ledger-card-expense-*`, `ledger-transfer-*` snippet으로 검증한다.

## 인증 상태와 CSRF

production 요청은 Cloudflare Access를 통과한 뒤 Spring Security가 `Cf-Access-Jwt-Assertion`을 다시 검증한다. 브라우저의 Access 인증 상태가 cookie로 유지되므로 상태 변경 요청의 CSRF 보호를 제거하지 않는다.

- frontend와 API는 same-origin이다. wildcard CORS를 구성하지 않는다.
- Spring Security 7 SPA mode와 `CookieCsrfTokenRepository`를 사용한다.
- 안전한 API 응답은 readable `XSRF-TOKEN` cookie와 `X-XSRF-TOKEN` response header를 발급한다.
- state-changing 요청은 cookie의 plain token을 `X-XSRF-TOKEN` request header로 함께 보낸다.
- token이 없거나 다르면 `403 CSRF_TOKEN_INVALID`다.

## 동시 수정

Transaction 등 충돌 가능 리소스는 version을 요청에 포함한다. 오래된 version이면 `409 Conflict`와 명시적 오류 코드를 반환한다.

## 멱등성

- 반복거래 생성은 DB unique로 보장
- 일반 POST의 idempotency key는 V1 기본 요구가 아님
- CSV export 같은 장시간 작업은 V1 데이터 규모에서는 동기 응답 가능

## 검증

field validation과 도메인 validation을 구분한다. HTTP status만으로 원인을 표현하지 않고 안정적인 error code를 제공한다.

API 계약 문서화 도구는 Spring REST Docs를 사용한다. request/response test가 생성한 snippet을 canonical API 문서에 조립하며, test를 통과하지 않은 hand-written response 예시만으로 구현 완료를 주장하지 않는다.
