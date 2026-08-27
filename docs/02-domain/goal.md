---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - ADR-006
  - 02-domain/financial-metrics.md
---

# Goal 도메인

## V1 Goal

- `MARRIAGE`: 결혼자금
- `CUSTOM`: 이후 확장을 위한 유형

V1 사용자 흐름은 활성 결혼자금 Goal 하나를 중심으로 한다.

## Account 연결

Goal은 자체 잔액을 직접 수정하지 않는다. `goal_accounts`로 실제 저축 Account를 연결하고 거래 원장에서 금액을 계산한다.

하나의 Account를 여러 활성 Goal에 동시에 연결하지 않는다. 같은 자산이 목표별로 중복 집계되는 것을 방지하기 위함이다.

## 지표

- 목표액: `target_amount`
- 현재 보유금: 연결 Account 현재 잔액 합계
- 누적 마련금: 연결 시 시작금액 + 비Goal Account에서 Goal Account로 유입된 순저축
- 사용된 목표자금: 누적 마련금 - 현재 보유금으로만 단정하지 않고 Goal Account에서 발생한 유효 EXPENSE와 외부 유출을 구분해 표시
- 달성률: 현재 보유금 / 목표액
- 예상 달성일: 최근 확정 기간의 월평균 순저축으로 추정

예상 월저축이 0 이하이거나 표본 기간이 부족하면 예상일을 반환하지 않는다.

## 연결 시 시작금액

기존 잔액이 있는 Account를 연결할 때 `starting_balance`를 저장한다. 이후 과거 거래가 수정되어 현재 잔액이 변할 수 있으므로 지표별 계산 기준과 수정 영향을 테스트한다.

## 금지

사용자가 Goal 기여금을 별도로 직접 추가하는 기능을 만들지 않는다. 저축은 항상 Transaction의 TRANSFER로 기록한다.
