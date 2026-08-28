---
status: active
version: 1.2
last_updated: 2026-08-29
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
/api/v1/calendar/month
/api/v1/budgets
/api/v1/recurring-transactions
/api/v1/goals/marriage
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
GET    /api/v1/transactions/{originalTransactionId}/refunds
POST   /api/v1/transactions/{originalTransactionId}/refunds
```

POST의 공통 필드는 `type`, positive `amount`, ISO 8601 `occurredAt`, nullable `memo`, `adjustmentType=NORMAL`, nullable `reversesTransactionId=null`이다. INCOME/EXPENSE는 `scope`, nullable `ownerMemberId/payerMemberId`, `categoryId`, `accountId`를 사용하고 source/destination은 null이다. TRANSFER는 scope/owner/payer/category/account가 null이고 `sourceAccountId`, `destinationAccountId`가 필수다. PATCH는 같은 필드와 현재 `version`을 요구한다.

response는 nullable owner/payer/Category, `version`, canonical `entries[]`, nullable `generatedFromRecurringId`/`recurrenceDate`를 포함한다. 수동 거래와 Refund의 provenance 두 field는 null이고 generated NORMAL 거래만 둘 다 값을 가진다. 각 Entry는 `id`, `role`, `balanceDelta`, Account reference를 제공하며 최상위 단일 `account`/`entry`는 제공하지 않는다. DELETE는 Transaction을 논리삭제하고 `204` 본문 없음으로 응답한다.

Refund POST는 원 NORMAL EXPENSE 하위 resource에서 `amount`, `occurredAt`, nullable `memo`만 받는다. Scope, Owner, Payer, Category, PRIMARY Account는 원 거래에서 파생하고 canonical `TransactionResponse`를 반환한다. generic Transaction POST의 `adjustmentType=REFUND`와 Refund generic PATCH는 허용하지 않는다.

Refund GET은 active Refund만 합산하고 다음 summary를 반환한다.

```json
{
  "originalTransactionId": 100,
  "originalAmount": 50000,
  "refundedAmount": 20000,
  "remainingRefundableAmount": 30000,
  "refunds": [
    {
      "id": 101,
      "amount": 20000,
      "occurredAt": "2026-08-28T03:00:00Z",
      "memo": "부분 환불",
      "version": 0
    }
  ]
}
```

current Household의 active `EXPENSE/NORMAL`과 valid PRIMARY Entry만 original이 될 수 있다. original row lock 뒤 cumulative cap을 검사한다. Refund DELETE는 기존 Transaction DELETE와 version 계약을 재사용한다. active Refund가 있는 original은 금융 edit/delete를 `409`로 거부하되 동일 금융 필드를 유지한 occurredAt/memo-only PATCH는 허용한다.

목록은 `occurred_at DESC, id DESC`로 정렬하고 다음 optional query를 고정한다.

| query | 의미 |
|---|---|
| `from`, `to` | Household timezone 기준 포함 날짜 `YYYY-MM-DD` |
| `type` | `INCOME`, `EXPENSE`, `TRANSFER` |
| `scope` | `PERSONAL` 또는 `SHARED` |
| `ownerMemberId` | PERSONAL owner Member ID |
| `categoryId` | Category ID |
| `accountId` | PRIMARY/SOURCE/DESTINATION 중 일치하는 Entry Account ID |

`from > to`는 `400 INVALID_REQUEST`다. 논리삭제 Transaction은 목록과 detail에서 제외한다. 실제 request/response는 `LedgerApiDocsTest`가 생성하는 `ledger-account-*`, `ledger-category-*`, `ledger-transaction-*`, `ledger-card-expense-*`, `ledger-transfer-*`, `ledger-refund-*` snippet으로 검증한다.

### Calendar month read model

```text
GET /api/v1/calendar/month?month=2026-08
GET /api/v1/calendar/month?month=2026-08&scope=PERSONAL&ownerMemberId=100
GET /api/v1/calendar/month?month=2026-08&scope=SHARED
```

`month`는 필수 `YYYY-MM`이다. scope와 owner가 모두 없으면 ALL, `PERSONAL`은 현재 Household의 `ownerMemberId`가 필수, `SHARED`는 owner가 없어야 한다. scope 없는 owner 또는 SHARED owner는 `400 INVALID_REQUEST`이고 다른 Household Member는 존재를 숨기는 `404 RESOURCE_NOT_FOUND`다. request에 `householdId`를 받지 않는다.

```json
{
  "month": "2026-08",
  "timezone": "Asia/Seoul",
  "summary": {
    "netSpendingAmount": 12000,
    "previousMonthNetSpendingAmount": 5000,
    "differenceAmount": 7000
  },
  "days": [
    {
      "date": "2026-08-01",
      "transactionCount": 1,
      "netSpendingAmount": 12000
    }
  ]
}
```

현재월과 이전월은 같은 Household timezone과 scope로 계산한다. 순소비는 `NORMAL EXPENSE - REFUND EXPENSE`이며 INCOME, TRANSFER, 논리삭제 거래는 0이다. TRANSFER는 ALL의 `transactionCount`에는 포함하지만 PERSONAL/SHARED에는 포함하지 않는다. `days`는 요청 월 안에서 거래가 존재하는 날짜만 반환하고 Calendar가 나머지 날짜를 0건·0원으로 채운다. 값은 Transaction에서 매번 파생하며 별도 집계 table이나 cache를 사용하지 않는다.

선택일 목록은 기존 `GET /api/v1/transactions?from={date}&to={date}`에 같은 scope/owner를 적용한다. 실제 월 request/response는 `LedgerApiDocsTest`의 `ledger-calendar-month` snippet으로 검증한다.

## Budget API

모든 Budget endpoint는 `CurrentHousehold.householdId`를 적용하고 request에 `householdId`를 받지 않는다.

```text
GET    /api/v1/budgets?month=2026-08
POST   /api/v1/budgets
PATCH  /api/v1/budgets/{budgetId}
DELETE /api/v1/budgets/{budgetId}?version={version}
```

### 생성과 수정

POST는 다음 identity와 amount를 받는다.

```json
{
  "month": "2026-08",
  "scope": "PERSONAL",
  "ownerMemberId": 100,
  "categoryId": 300,
  "amount": 300000
}
```

PATCH는 같은 field에 현재 `version`을 추가한다. V1은 month/scope/owner/category/amount를 함께 수정할 수 있다.

- HOUSEHOLD/SHARED는 `ownerMemberId=null`, PERSONAL은 current Household Member ID가 필수다.
- `categoryId=null`은 해당 Scope 전체이며 값이 있으면 active EXPENSE Category만 허용한다.
- amount는 0 이상 정수다.
- 같은 identity의 service pre-check와 DB unique race는 모두 `409 BUDGET_DUPLICATE`다.
- stale PATCH/DELETE는 `409 BUDGET_VERSION_CONFLICT`다.
- 다른 Household Budget/Member/Category는 미존재와 같은 `404 RESOURCE_NOT_FOUND`다.
- DELETE는 Budget row만 제거하며 Transaction을 변경하지 않는다.

mutation response는 canonical `id`, `month`, `scope`, nullable owner/category, `amount`, `version`, timestamp를 반환한다.

### 월 read model

GET은 Budget row와 Transaction 파생 사용액의 단일 화면 계약이다.

```json
{
  "month": "2026-08",
  "timezone": "Asia/Seoul",
  "scopes": [
    {
      "scope": "HOUSEHOLD",
      "owner": null,
      "budgetId": 1,
      "version": 0,
      "budgetAmount": 1500000,
      "spentAmount": 1284500,
      "remainingAmount": 215500,
      "exceeded": false
    },
    {
      "scope": "PERSONAL",
      "owner": {
        "memberId": 100,
        "userId": 1,
        "displayName": "실제 Member"
      },
      "budgetId": null,
      "version": null,
      "budgetAmount": null,
      "spentAmount": 420000,
      "remainingAmount": null,
      "exceeded": false
    }
  ],
  "categories": []
}
```

`scopes`는 HOUSEHOLD, current Household의 각 실제 Member PERSONAL, SHARED를 Budget 설정 여부와 무관하게 포함한다. 미설정은 `budgetId/version/budgetAmount/remainingAmount=null`이다. `categories`는 실제 생성된 Category Budget만 반환하고 archived Category도 `archived=true`로 식별한다.

사용액은 같은 month/scope/category의 `NORMAL EXPENSE - REFUND EXPENSE`다. INCOME, TRANSFER, 논리삭제는 제외한다. 실제 request/response는 `BudgetApiDocsTest`의 `budget-create`, `budget-month`, `budget-update`, `budget-delete`, Budget conflict snippet으로 검증한다.

## Recurring API

모든 endpoint는 `CurrentHousehold.householdId`를 적용하며 request에 `householdId`를 받지 않는다. V1에서는 규칙 삭제 대신 일시정지와 재개를 사용한다.

```text
GET   /api/v1/recurring-transactions
POST  /api/v1/recurring-transactions
PATCH /api/v1/recurring-transactions/{recurringTransactionId}
```

create/update는 다음 template과 schedule을 전체 필드로 받는다.

- template: `name`, `type`, positive `amount`, nullable `scope`, nullable `ownerMemberId`/`payerMemberId`/`categoryId`, 거래 유형에 따른 `accountId` 또는 `sourceAccountId`/`destinationAccountId`, nullable `memo`
- schedule: `frequency=DAILY|WEEKLY|MONTHLY|YEARLY`, positive `intervalValue`, `startDate`, nullable `endDate`, `scheduledLocalTime`
- execution: `autoPost=true`, `active`; PATCH는 현재 `version`을 추가로 요구한다.

template의 Scope, Member, Category, Account와 posting 조합은 수동 Transaction과 같은 canonical validation을 사용한다. 규칙은 잔액이나 통계의 원장이 아니며, 실행 시 canonical `NORMAL` Transaction과 Entry를 생성한다. 생성 거래 response의 `generatedFromRecurringId`와 `recurrenceDate`가 원 규칙과 발생일을 식별한다.

response는 template/schedule 외에 role별 `accounts[]`, `nextRecurrenceDate`, `status=ACTIVE|PAUSED|ENDED`, `version`, timestamp를 반환한다. 목록은 규칙 ID 오름차순이며 active, paused, ended를 모두 포함한다. 종료일을 지난 active 규칙은 `ENDED`, 사용자가 끈 규칙은 `PAUSED`다.

- Household timezone의 local date/time을 실제 실행 시각으로 해석한다.
- MONTHLY/YEARLY는 최초 start date의 day/month anchor를 보존하고 짧은 달과 윤년에는 해당 월의 마지막 날로 clamp한다.
- 일시정지 중 발생일은 재개 시 소급 생성하지 않고 재개 시각 이후의 첫 발생일로 cursor를 이동한다.
- 활성 규칙의 template 수정은 이미 생성된 Transaction을 바꾸지 않으며 다음 발생부터 snapshot으로 적용한다.
- 한 번의 scheduler poll은 설정된 최대 발생 수까지만 처리하고, 발생일 하나마다 별도 Transaction을 만든다.
- 규칙 row lock 아래 due 여부를 다시 확인하고 Transaction 생성과 cursor 이동을 하나의 transaction으로 처리한다.
- `(generated_from_recurring_id, recurrence_date)` unique는 논리삭제된 생성 거래까지 포함해 재생성을 차단한다.
- active 규칙이 참조하는 Account, Category, Category Group은 archive 또는 posting 의미 변경을 `409 RECURRING_REFERENCE_IN_USE`로 거부한다.

실제 request/response와 CSRF, Household 격리, version conflict는 `RecurringApiDocsTest`의 `recurring-create`, `recurring-list`, `recurring-update`, `recurring-version-conflict` snippet으로 검증한다.

## Marriage Goal API

모든 endpoint는 `CurrentHousehold.householdId`를 적용하며 request에 `householdId`, `startingBalance`, `linkedAt`을 받지 않는다.

```text
GET    /api/v1/goals/marriage
POST   /api/v1/goals/marriage
PATCH  /api/v1/goals/marriage
POST   /api/v1/goals/marriage/accounts/{accountId}
DELETE /api/v1/goals/marriage/accounts/{accountId}
```

Goal 부재는 오류가 아닌 정상 제품 상태다. GET은 항상 wrapper를 반환하며 없을 때 `goal=null`, 연결 가능한 active 저축 ASSET 목록을 `eligibleAccounts`로 제공한다.

```json
{
  "goal": null,
  "eligibleAccounts": [
    {
      "id": 201,
      "name": "결혼 적금",
      "ownership": "PERSONAL",
      "owner": {"memberId": 100, "displayName": "Owner"},
      "currentBalance": 5000000
    }
  ]
}
```

POST는 `name`, positive `targetAmount`를 받는다. PATCH는 같은 값과 현재 `version`을 받는다. Household의 MARRIAGE Goal은 최대 한 개이며 stale 수정과 concurrent create는 각각 `GOAL_VERSION_CONFLICT`, `GOAL_ALREADY_EXISTS` 409다. physical delete는 제공하지 않는다.

Account link POST는 path ID만 받는다. server가 Account row write lock을 잡은 뒤 current balance를 계산하고 `startingBalance`, `linkedAt`, actor를 같은 transaction에서 저장한다. active ASSET, `savings_enabled=true`, 미할당 Account만 연결할 수 있다. DELETE는 link만 제거하고 Account/Transaction/Entry를 바꾸지 않는다. foreign Account/link는 일반화된 404, ineligible은 `GOAL_ACCOUNT_NOT_ELIGIBLE` 422, concurrent assignment는 `GOAL_ACCOUNT_ALREADY_ASSIGNED` 409다.

Goal read model의 `goal`은 다음 필드를 제공한다.

- identity: `id`, `type=MARRIAGE`, `name`, `targetAmount`, `version`, timestamp
- current: `currentAmount`, 소수점 한 자리 `achievementRate`, `remainingAmount`
- flow/projection: `thisMonthSavingsAmount`, nullable `recentAverageMonthlySavingsAmount`, `projectionStatus`, nullable `expectedAchievementMonth`
- evidence: 고정 6개 `monthlyTrend`, `linkedAccounts`, 최대 10개 `recentSavingsActivities`

`linkedAccounts`는 name, ownership, nullable owner, current/starting balance, linkedAt, archived만 제공한다. archive된 기존 link도 unlink 전까지 유지한다. 최근 활동은 impact가 0이 아닌 Transfer의 ID/occurredAt/amount/Goal impact/source·destination ID·name/memo와 nullable recurring provenance만 제공하며 전체 계좌번호를 노출하지 않는다.

이번 달과 월별 추이는 Household timezone calendar month다. current month의 future occurrence를 임의 제거하지 않는다. 직전 완료 3개월 표본이 부족하면 평균은 null과 `INSUFFICIENT_HISTORY`, 평균이 0 이하면 `NON_POSITIVE_AVERAGE`, 달성하면 `ACHIEVED`, 양수 평균으로 예상 가능하면 `PROJECTED`와 `YYYY-MM`을 반환한다.

실제 request/response와 CSRF/error는 `MarriageGoalApiDocsTest`의 `marriage-goal-*` snippet으로 검증한다.

## Statistics read model

```text
GET /api/v1/statistics?from=2026-08-01&to=2026-08-31&compareFrom=2026-07-01&compareTo=2026-07-31
GET /api/v1/statistics?...&scope=PERSONAL&ownerMemberId=100
GET /api/v1/statistics?...&scope=SHARED
GET /api/v1/statistics/savings-activities?from=2026-08-01&to=2026-08-31
```

모든 날짜는 current Household timezone의 포함 날짜다. `from/to`는 필수이며 역전할 수 없다. `compareFrom/compareTo`는 둘 다 있거나 둘 다 없어야 한다. Scope와 owner 조합은 Calendar와 같고 다른 Household Member는 `404 RESOURCE_NOT_FOUND`다. request에 `householdId`를 받지 않는다.

`GET /api/v1/statistics`는 다음 의미를 가진다.

- `period`: current `from/to/timezone`
- `summary`: NORMAL INCOME, NORMAL EXPENSE - REFUND EXPENSE, nullable savings amount/rate
- `comparison`: 이전 기간 값, current-previous 금액 차이, percent change, savings rate percentage point 차이. 비교 범위가 없으면 `null`이다.
- `subjects`: 실제 Member PERSONAL과 SHARED 순소비. filtered view에는 현재 filter 밖 bucket을 섞지 않는다.
- `categories`: current canonical name, archived, 순소비, nullable share rate
- `accounts`: EXPENSE/REFUND PRIMARY Account reference와 순소비
- `months`: current range가 걸친 모든 calendar month. 빈 달도 0 row이며 partial month는 실제 범위만 계산한다.

비율은 소수점 한 자리 `HALF_UP`이다. 이전 금액이 0이면 percent change는 `null`, income이 0이면 savings rate는 `null`이다. Transfer에는 Scope가 없으므로 PERSONAL/SHARED의 savings amount/rate와 관련 comparison/month 값은 `null`이다.

`savings-activities`는 비저축 ASSET→저축 ASSET의 양수 impact와 저축 ASSET→비저축 목적지의 음수 impact만 반환한다. impact가 0인 Transfer, 논리삭제 Transaction, 다른 Household data는 제외하며 item은 Transaction ID, occurredAt, 원 amount, savings impact, source/destination Account의 ID·name, memo만 포함한다. item impact 합은 같은 기간 ALL summary savings amount와 일치한다.

실제 request/response는 `StatisticsApiDocsTest`의 `statistics-read-model`, `statistics-savings-activities`, `statistics-invalid-request` snippet으로 검증한다. Statistics는 별도 table/cache가 없는 원장 파생 read model이다.

## Assets read model

```text
GET /api/v1/assets
```

request에 Household ID나 기간·소유 filter를 받지 않는다. 인증된 current Household의 actual Member, active·archived Account와 유효 Account Entry만 읽으며 다른 Household data는 포함하지 않는다. 응답은 한 repeatable-read transaction에서 다음을 제공한다.

- `asOf`, Household `timezone`
- `household`: signed `totalAssets`, signed `totalLiabilities`, `netWorth=totalAssets-totalLiabilities`
- `members`: actual Member ID·display name과 PERSONAL Account 기준 세 값
- `shared`: SHARED Account 기준 세 값
- `accounts`: ID·name·nullable institution, type/nature/ownership, nullable owner, opening balance/date, ledger delta, current balance, currency, savings/archive/sort 상태
- `monthlyTrend`: Household timezone 기준 직전 11개 완료 월말과 현재 한 점의 month, complete, asOf, assets, liabilities, netWorth

Account는 ASSET→LIABILITY, actual Member PERSONAL→SHARED, `sortOrder`, ID 순으로 안정 정렬한다. 음수와 0 balance를 제거하거나 clamp하지 않으며 archived Account도 포함한다. `lastFour`와 전체 계좌번호는 응답하지 않는다. 현재 trend 점은 같은 응답의 Household summary와 정확히 일치한다.

과거 월은 Account opening date 이전 기여도를 0으로 보고 해당 월말까지의 active Transaction Entry를 합산한다. 논리삭제 Transaction은 제외하고 generated recurring Transaction은 일반 원장과 동일하게 포함한다. Goal link/unlink는 결과를 바꾸지 않는다. 별도 Assets aggregate table이나 cache는 사용하지 않는다.

실제 response와 인증 오류는 `AssetsApiDocsTest`의 `assets-read-model`, `assets-authentication-required` snippet으로 검증한다.

## 인증 상태와 CSRF

production 요청은 Cloudflare Access를 통과한 뒤 Spring Security가 `Cf-Access-Jwt-Assertion`을 다시 검증한다. 브라우저의 Access 인증 상태가 cookie로 유지되므로 상태 변경 요청의 CSRF 보호를 제거하지 않는다.

- frontend와 API는 same-origin이다. wildcard CORS를 구성하지 않는다.
- Spring Security 7 SPA mode와 `CookieCsrfTokenRepository`를 사용한다.
- 안전한 API 응답은 readable `XSRF-TOKEN` cookie와 `X-XSRF-TOKEN` response header를 발급한다.
- state-changing 요청은 cookie의 plain token을 `X-XSRF-TOKEN` request header로 함께 보낸다.
- token이 없거나 다르면 `403 CSRF_TOKEN_INVALID`다.

## 동시 수정

Transaction, Recurring Transaction, Budget, Goal 등 충돌 가능 리소스는 version을 요청에 포함한다. 오래된 version이면 `409 Conflict`와 명시적 오류 코드를 반환한다.

## 멱등성

- 반복거래 생성은 DB unique로 보장
- 일반 POST의 idempotency key는 V1 기본 요구가 아님
- CSV export 같은 장시간 작업은 V1 데이터 규모에서는 동기 응답 가능

## 검증

field validation과 도메인 validation을 구분한다. HTTP status만으로 원인을 표현하지 않고 안정적인 error code를 제공한다.

API 계약 문서화 도구는 Spring REST Docs를 사용한다. request/response test가 생성한 snippet을 canonical API 문서에 조립하며, test를 통과하지 않은 hand-written response 예시만으로 구현 완료를 주장하지 않는다.
