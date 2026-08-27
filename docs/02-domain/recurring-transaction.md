---
status: active
version: 0.1
last_updated: 2026-08-27
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

## Idempotency

생성 Transaction에 다음을 저장한다.

- `generated_from_recurring_id`
- `recurrence_date`

둘의 조합은 유일해야 한다. 스케줄러 재시작이나 중복 실행이 같은 거래를 두 번 만들면 안 된다.

## 날짜 규칙

- Household timezone 기준으로 due date를 판단한다.
- 월말보다 큰 일자는 해당 월 마지막 날 처리 여부를 제품 규칙으로 고정한다. V1 기본은 마지막 날로 보정한다.
- `end_date` 이후에는 생성하지 않는다.
- 비활성화된 규칙은 미래 거래를 만들지 않지만 이미 생성된 거래를 삭제하지 않는다.

## 자동 반영

`auto_post=true`는 즉시 실제 거래를 만든다. 예정 거래 승인 흐름은 V1 MUST가 아니며 필요 시 후속 Slice로 분리한다.
