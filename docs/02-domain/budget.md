---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 02-domain/financial-metrics.md
  - 05-frontend/budget-screen.md
---

# Budget 도메인

## 기간

Budget은 월 단위이며 `budget_month`는 해당 월 1일로 저장한다. Household timezone 기준 월이다.

## Scope

- `HOUSEHOLD`: 개인과 공동 소비를 합한 전체 예산
- `PERSONAL`: 특정 Owner의 개인 소비 예산
- `SHARED`: 공동 소비 예산

Category는 선택이다. Category가 없으면 해당 Scope 전체, 있으면 세부 Category 예산이다.

## 계산

Budget 사용액은 같은 월·Scope·Category 조건의 순소비다.

```text
사용액 = NORMAL EXPENSE - REFUND EXPENSE
```

TRANSFER와 INCOME은 포함하지 않는다. 삭제 거래는 제외한다.

## V1 규칙

- 월간 예산은 서로 독립적이다.
- 미사용 금액 자동 이월은 하지 않는다.
- 음수 예산을 허용하지 않는다.
- 전체 예산과 세부 예산이 동시에 있어도 세부 합계가 전체와 같아야 한다고 강제하지 않는다.
- 예산 초과는 거래 저장을 차단하지 않고 경고만 제공한다.
