---
status: active
version: 0.5
last_updated: 2026-08-28
related:
  - 01-product/user-flows.md
  - 02-domain/transaction.md
  - 05-frontend/design-system.md
  - 05-frontend/interaction-motion.md
---

# 빠른 입력

## 목표

일반 지출은 한 화면에서 최소 입력으로 저장한다.

이 문서는 Quick Entry의 활성 디자인 계약이다. 실제로 활성화할 거래 유형과 API field는 해당 Slice Issue 및 domain/API 문서가 최종 authority다.

## 진입과 Sheet

- Home의 중앙 Paw FAB를 선택하면 viewport 높이의 약 85~90%인 Bottom Sheet를 연다.
- Sheet가 열린 뒤 금액 input에 자동 focus한다.
- V1 금액 입력은 native numeric keyboard를 우선한다.
- 닫기, system back, focus 복귀가 일관돼야 하며 입력 중 실수로 닫힐 가능성을 줄인다.

## 기본 순서

1. `지출 / 수입 / 이체`
2. 금액
3. `치호 / 여자친구 / 공동`
4. Category
5. Account
6. 날짜
7. 필요한 경우 Payer
8. 메모와 상세 옵션
9. 저장

지출에서는 필요 시 Payer를 확인한다. 수입에서는 Owner 또는 Shared 범위를 선택한다. 이체에서는 source와 destination을 선택하고 Scope/Category/Payer를 숨긴다.

## 거래 유형별 field

| 유형 | 표시하는 핵심 field | 숨기는 field |
|---|---|---|
| `EXPENSE` | 금액, Scope/Owner, Expense Category, 결제 Account, 날짜, 필요한 경우 Payer | 없음 |
| `INCOME` | 금액, Scope/Owner, Income Category, 입금 Account, 날짜 | Payer |
| `TRANSFER` | 금액, source Account, destination Account, 날짜 | Scope/Owner, Category, Payer |

- Owner/Scope는 거래의 귀속이고 Payer는 실제 결제자이므로 하나의 값으로 합치지 않는다.
- Scope 선택에는 고양이 identity를 signature interaction으로 사용할 수 있지만 실제 Member 이름과 `공동` text를 항상 함께 표시한다.
- 거래 유형을 바꿔 기존 Category가 유효하지 않게 되면 임의로 다른 Category를 선택하지 않고 값을 해제해 사용자가 다시 선택하게 한다.
- 숨긴 field의 이전 값은 submit payload에 남지 않아야 한다.

## 기본값

- 날짜: Calendar에서 열면 선택 날짜, 그 밖의 진입에서는 오늘
- 통화: KRW
- Account: 최근 사용값 또는 사용자 기본값
- Owner/Payer: `/api/v1/me.userId`와 Household Member의 `userId`가 일치하는 현재 사용자
- Scope: 최근값을 무조건 재사용해 오입력을 유발하지 않도록 명확히 표시

자동 선택된 Account와 날짜는 사용자가 저장 전에 식별할 수 있게 명시한다.

## Category Picker

Quick Entry에는 현재 거래 유형에서 최근 사용한 서로 다른 Category를 최대 4개 정도 chip으로 노출하고 `전체` action을 제공한다.

전체 Category Bottom Sheet는 다음 순서를 따른다.

1. 검색
2. 최근 사용
3. Category Group별 icon grid

- `INCOME`과 `EXPENSE` Category를 완전히 분리한다.
- archive된 Category는 신규 선택에서 제외한다.
- 선택 즉시 Quick Entry에 반영하고 picker를 닫으며 별도 확인 button을 두지 않는다.
- Concept 단계의 emoji는 placeholder일 뿐 production Category asset 계약이 아니다.

## Account Picker

- Quick Entry에는 현재 선택한 Account 이름을 가장 강하게 표시하고 owner, 기관, 식별 가능한 최소 정보, 필요 시 잔액을 secondary 정보로 둔다.
- 전체 picker는 `최근 / 실제 Member별 / 공동` section grouping을 우선한다.
- 거래 Scope와 Account ownership은 독립적이다. 공동 지출이라는 이유로 공동 Account만 보여 주지 않는다.
- 거래 유형상 허용되는 active Account 전체를 보여 주되 ownership별로 묶는다.
- 최근 Account 자동 선택과 거래 유형별 최근값 기억은 허용하지만 현재 선택값을 명확히 표시한다.
- 전체 계좌번호나 금융 식별정보를 표시하거나 log에 남기지 않는다.

## 날짜와 시간

- `오늘 / 어제 / 다른 날짜` shortcut을 제공하고 오늘을 기본값으로 한다.
- `다른 날짜`는 Calendar picker를 열며 선택 즉시 Quick Entry에 반영한다.
- 정확한 시간은 `메모 및 상세`에서 수정한다.
- 과거 날짜만 바꾸고 시간을 직접 수정하지 않은 경우 입력 시점 clock time을 유지하는 방식을 우선 검토한다.
- 저장되는 최종 값과 validation은 Transaction domain/API의 `occurred_at` 계약을 따른다.

## 고급 옵션

- 메모
- 정확한 시간
- 반복 설정
- 환불은 원 거래 상세에서 진입

## 유효성

- 금액은 1원 이상
- source와 destination 동일 금지
- 개인 거래 Owner 필수
- shared 거래 Owner 없음
- Category type 일치
- archive된 Account/Category 신규 선택 금지

client validation은 server의 Household, ownership, 거래 유형, Account/Category 상태 검증을 대체하지 않는다.

## 저장 후

성공 흐름은 다음 순서를 따른다.

1. 저장 button 비활성화와 spinner로 중복 submit 방지
2. `저장했어요` text와 작은 Paw feedback 표시
3. 약 400~600ms 뒤 Bottom Sheet 닫기
4. 달력·예산·자산의 관련 query, 숫자, 거래 목록 갱신

실패하면 Sheet와 모든 입력값을 유지하고 오류 원인을 표시해 재시도할 수 있게 한다. V1에서는 `저장 후 계속 입력`을 기본 제공하지 않는다.

## Slice 4 구현 상태

- 현재 Household의 Account를 이름, type, PERSONAL/SHARED owner, 기초 잔액·기준일로 생성하고 active 목록에서 archive할 수 있다.
- Category Group과 Category를 지출/수입 type으로 생성하고 active 목록에서 archive할 수 있다. Group 없는 Category를 허용한다.
- 빠른 입력은 Home Paw FAB에서 86dvh Bottom Sheet로 열리고 금액 input을 autofocus한다. 닫기·ESC·browser back 뒤 opener focus를 복원한다.
- 빠른 입력은 지출/수입/이체와 양수 금액을 받는다. 수입은 active ASSET, 지출은 active ASSET 또는 CREDIT_CARD/LIABILITY, 이체 source는 active ASSET, destination은 다른 active ASSET/LIABILITY만 선택한다.
- 이체에서는 Scope/Owner/Payer/Category/PRIMARY Account를 숨기고 source/destination을 표시한다.
- Account 생성에서 CREDIT_CARD를 선택하면 LIABILITY를 강제하고 savings를 비활성화한다.
- 선택일 목록은 `occurredAt DESC, id DESC`의 API 순서를 그대로 표시한다. 이체는 source→destination, 카드 지출은 카드 Account를 표시하며 edit/delete는 조회한 `version`을 사용한다.
- mutation helper는 same-origin `XSRF-TOKEN` cookie를 `X-XSRF-TOKEN` header로 보낸다. pending 동안 해당 submit/delete button을 비활성화한다.
- 서버 validation/domain 실패 시 Account/Category/Transaction form state를 초기화하지 않고 error message를 `role=alert`로 표시한다.
- 성공 시 `저장했어요/수정했어요 🐾`를 500ms 표시한 뒤 Sheet를 닫고 같은 월·Scope·선택일을 갱신한다. Calendar Scope와 무관하게 현재 사용자의 PERSONAL을 신규 입력 기본값으로 사용한다.

최근 Category chip·검색·Group icon grid와 Account section picker는 이 Slice에서 새 dependency나 가짜 최근 사용 data 없이 기존 native select를 유지한다. 해당 picker 정교화는 실제 최근 사용 계약과 production asset을 함께 정의하는 후속 범위다.
