---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - ADR-002
  - ADR-003
  - ADR-004
---

# Transaction 도메인

## Transaction Type

- `INCOME`: 자금 유입
- `EXPENSE`: 소비 또는 소비 환불
- `TRANSFER`: Account 사이 이동

금액 `amount`는 항상 0보다 큰 KRW 정수다. 방향은 type, adjustment, Account Entry의 `balance_delta`로 표현한다.

## Scope

`INCOME`과 `EXPENSE`는 다음 중 하나다.

- `PERSONAL`: `owner_member_id` 필수
- `SHARED`: `owner_member_id` 없음

`TRANSFER`에는 Scope, Owner, Category가 없다.

## Owner와 Payer

- Owner: 개인 수입·소비의 귀속자
- Payer: 지출을 실제 결제한 Member

Payer는 정산 계산에 사용하지 않는다. 공유 Account로 결제해 특정 Payer를 정하기 어려운 경우 nullable을 허용할 수 있으나, UI와 서비스 규칙은 가능한 한 실제 결제자를 기록한다.

## Category

- `INCOME`: INCOME Category 필수
- `EXPENSE`: EXPENSE Category 필수
- `TRANSFER`: Category 없음

## Adjustment

- `NORMAL`: 일반 거래
- `REFUND`: 기존 NORMAL EXPENSE를 상쇄

REFUND는 원 거래 `reverses_transaction_id`를 필수로 참조한다. 원 거래와 같은 Household여야 하며 누적 환불 금액은 원 거래액을 초과할 수 없다.

## 수정과 삭제

- 오입력: 원 거래 수정 또는 논리삭제
- 실제 가맹점 환불: REFUND 거래 생성
- 삭제된 거래는 Account 잔액과 모든 계산에서 제외
- optimistic locking으로 오래된 화면의 덮어쓰기를 방지

## 시간

`occurred_at`은 `TIMESTAMPTZ`로 저장한다. 월·일 계산은 Household timezone인 `Asia/Seoul` 기준으로 한다.

## Slice 2 실행 계약

- API/Service는 `INCOME`, `EXPENSE`와 `adjustment_type=NORMAL`만 생성·수정한다.
- `TRANSFER`, `REFUND`, CREDIT_CARD/LIABILITY posting은 schema enum으로 표현될 수 있어도 stable `422` error code로 거부한다.
- INCOME에는 payer를 지정하지 않고 EXPENSE payer는 nullable이다.
- 생성자·수정자·삭제자 audit ID는 요청을 수행한 current HouseholdMember ID다.
- PATCH와 DELETE는 현재 `version`을 요구한다. stale version은 `409 TRANSACTION_VERSION_CONFLICT`로 거부한다.
- 기본 목록은 논리삭제를 제외하고 `occurred_at DESC, id DESC`로 정렬한다.
- 목록 필터는 `from`, `to`, `type`, `scope`, `ownerMemberId`, `categoryId`, `accountId`다. `from`/`to`는 current Household timezone의 날짜 경계를 포함한다.
