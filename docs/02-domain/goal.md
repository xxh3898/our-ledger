---
status: active
version: 1.0
last_updated: 2026-08-29
related:
  - ADR-006
  - 02-domain/financial-metrics.md
---

# Goal 도메인

## V1 Goal

- `MARRIAGE`: 결혼자금
- `CUSTOM`: 이후 확장을 위한 유형

V1 공개 사용자 흐름은 current Household의 결혼자금 Goal 0개 또는 1개를 중심으로 한다. `CUSTOM`은 schema 확장성만 유지하며 공개 생성 API/UI를 제공하지 않는다. 이름과 양수 KRW `target_amount`는 수정할 수 있고 물리삭제는 제공하지 않는다.

## Account 연결

Goal은 자체 잔액을 직접 수정하지 않는다. `goal_accounts`로 실제 저축 Account를 연결하고 거래 원장에서 금액을 계산한다.

하나의 Account를 여러 Goal에 동시에 연결하지 않는다. 같은 자산이 목표별로 중복 집계되는 것을 방지하기 위함이다. 신규 연결은 current Household의 active `ASSET`, `savings_enabled=true`, 미할당 Account만 허용하며 PERSONAL/SHARED ownership은 모두 가능하다.

연결과 같은 Account의 Transaction posting은 Account row `PESSIMISTIC_WRITE` lock에서 직렬화한다. 잠금 획득 뒤 현재 잔액을 계산하고 같은 transaction에서 `starting_balance`, server `linked_at`, actor Member를 저장한다. 연결 해제는 link만 제거하며 Account, Transaction, Entry를 변경하지 않는다.

이미 연결된 Account가 이후 archive돼도 명시적으로 unlink할 때까지 현재 잔액과 `archived=true` 상태를 Goal read model에 유지한다. 다시 연결하면 당시 실제 잔액과 새 연결 시각으로 snapshot을 만든다.

## 지표

- 목표액: `target_amount`
- 현재 보유금: 연결 Account 현재 잔액 합계
- 달성률: 현재 보유금 / 목표액
- 남은 금액: `max(target_amount - 현재 보유금, 0)`
- 이번 달 순저축: Household timezone 현재 calendar month의 Goal 경계 TRANSFER 합
- 최근 월평균: 최근 완료된 3개 calendar month의 Goal 순저축 정수 평균
- 예상 달성 월: 최근 월평균으로 남은 금액을 채우는 데 필요한 월 수를 올림해 현재 월에 더한 값

달성률은 소수점 한 자리 `HALF_UP`이며 100%를 넘거나 음수가 될 수 있다. 시각 progress만 0~100으로 clamp한다. 예상은 `ACHIEVED`, `INSUFFICIENT_HISTORY`, `NON_POSITIVE_AVERAGE`, `PROJECTED` 상태를 명시하며 계산 불가 이유를 null 하나로 숨기지 않는다.

## Goal 순저축 경계

현재 연결과 각 Account의 `linked_at`이 Transaction 발생 시점에 유효한지를 기준으로 `TRANSFER`만 분류한다.

```text
비Goal source → Goal destination       +amount
Goal source → 비Goal destination       -amount
Goal source → Goal destination          0
비Goal source → 비Goal destination      0
```

- 다른 `savings_enabled=true` Account에서 Goal로 들어와도 Goal 관점에서는 양수다.
- Goal Account 사이 이동은 신규 저축이 아니다.
- EXPENSE, REFUND, INCOME은 실제 Account 잔액을 통해 현재 보유금에는 반영되지만 Goal 순저축으로 재분류하지 않는다.
- logical delete Transaction과 `linked_at` 이전 발생 거래는 제외한다.
- Recurring-generated TRANSFER도 같은 규칙으로 계산하고 provenance를 유지한다.

## 연결 시 시작금액

기존 잔액이 있는 Account를 연결할 때 `starting_balance`를 저장한다. 이 값은 연결 직전 실제 잔액의 audit snapshot이며 현재 보유금에 다시 더하지 않는다. 현재 보유금은 언제나 연결 Account별 `opening_balance + active Entry balance_delta`의 현재 합이다.

## 금지

사용자가 Goal 기여금을 별도로 직접 추가하는 기능을 만들지 않는다. 저축은 항상 Transaction의 TRANSFER로 기록한다.
