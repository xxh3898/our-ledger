---
status: active
version: 1.0
last_updated: 2026-08-28
related:
  - ADR-005
  - 07-quality/financial-invariants.md
---

# 반복거래 도메인

## 목적

월급, 구독, 보험, 적금처럼 반복되는 거래를 매번 입력하지 않도록 실제 Transaction을 생성하는 규칙이다.

## 주기

- `DAILY`
- `WEEKLY`
- `MONTHLY`
- `YEARLY`

`interval_value`로 2주, 4주, 3개월 등 복합 주기를 표현한다.

## 실행 모델

RecurringTransaction 자체는 통계·잔액에 포함되지 않는다. 스케줄러가 recurrence date별 일반 Transaction과 Account Entry를 생성한다.

- `next_recurrence_date`는 다음 생성 후보를 가리키는 operational cursor다.
- 한 occurrence transaction에서 rule row lock, due 재확인, Transaction/Entry 생성, cursor advance를 모두 수행한다.
- generated Transaction은 생성 시점 template의 snapshot이며 이후 rule 수정과 독립적으로 일반 거래처럼 수정·논리삭제할 수 있다.
- generated 거래를 수정·삭제해도 rule이나 cursor를 역으로 변경하지 않는다.

## Idempotency

생성 Transaction에 다음을 저장한다.

- `generated_from_recurring_id`
- `recurrence_date`

둘의 조합은 유일해야 한다. 스케줄러 재시작이나 중복 실행이 같은 거래를 두 번 만들면 안 된다.

유일성은 논리삭제된 generated Transaction도 포함한다. generation transaction은 rule row를 `PESSIMISTIC_WRITE`로 잠그고 기존 occurrence를 확인하며 database unique constraint를 최종 방어선으로 사용한다.

## 날짜 규칙

- Household timezone 기준으로 due date를 판단한다.
- `start_date`가 schedule anchor다.
- DAILY는 `interval_value`일, WEEKLY는 `7 * interval_value`일 간격이다.
- MONTHLY는 start day-of-month, YEARLY는 start month/day를 매번 원 anchor에서 계산한다.
- 월에 anchor day가 없으면 해당 월 마지막 날로 clamp하되 다음 달에는 원 anchor를 복원한다.
- 2월 29일 yearly도 non-leap year에 2월 말일로 clamp하고 다음 leap year에 29일을 복원한다.
- `end_date` 이후에는 생성하지 않는다.
- `scheduled_local_time`은 Household local time이며 generated `occurred_at`은 generation clock이 아니라 recurrence date와 이 local time으로 계산한다.

## 생성과 변경

- 신규 `start_date`는 Household 오늘보다 과거일 수 없다. 오늘 시간이 지났다면 첫 poll이 해당 occurrence를 catch-up할 수 있다.
- 서버 중단 중 놓친 active occurrence는 cursor부터 순서대로 bounded batch 안에서 catch-up한다.
- `active=false`는 미래 생성을 중지하지만 cursor와 history를 삭제하지 않는다.
- resume은 paused 기간을 backfill하지 않고 현재 시각 이후 첫 schedule occurrence로 cursor를 다시 계산한다.
- frequency, interval, start date, local time 변경도 과거를 소급하지 않고 현재 시각 이후 schedule부터 적용한다.
- final occurrence 뒤 `next_recurrence_date=null`이면 row를 유지한 ended 상태다.
- user PATCH는 optimistic `version`을 요구한다.

## Template posting

- INCOME/EXPENSE는 PRIMARY Account 1개, TRANSFER는 SOURCE/DESTINATION 각 1개를 저장한다.
- template table에는 `balance_delta`를 저장하지 않는다. 실제 생성 시 canonical Transaction posting 검증과 Entry 계산을 재사용한다.
- V1은 NORMAL INCOME/EXPENSE와 ASSET source TRANSFER만 지원한다. recurring REFUND와 LIABILITY source는 지원하지 않는다.
- generated audit actor는 생성 시점 rule의 `updated_by` HouseholdMember다.

## 기준정보 lifecycle

active이며 next occurrence가 있는 rule의 Account/Category/Group은 미래 posting reference다. archive나 호환되지 않는 Account posting 분류 변경은 `RECURRING_REFERENCE_IN_USE`로 차단한다. paused/ended rule은 archive를 막지 않지만 resume 시 active·posting-compatible reference를 다시 검증한다.

## 자동 반영

V1은 `auto_post=true`만 지원한다. 예정 거래 승인 흐름과 `auto_post=false`는 후속 Slice다.
