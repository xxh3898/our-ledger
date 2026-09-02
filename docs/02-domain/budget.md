---
status: active
version: 0.3
last_updated: 2026-09-02
related:
  - 02-domain/financial-metrics.md
  - 05-frontend/budget-screen.md
---

# Budget 도메인

## 기간

Budget은 월 단위이며 `budget_month`는 해당 월 1일로 저장한다. Household timezone 기준 월이다.

## Scope

- `HOUSEHOLD`: 개인과 공동 소비 전체에 적용하는 독립 월 한도. 각 `PERSONAL` Budget amount 합의 파생값이 아니다.
- `PERSONAL`: 특정 Owner의 개인 소비 예산
- `SHARED`: 공동 소비 예산

Category는 선택이다. Category가 없으면 해당 Scope 전체, 있으면 세부 Category 예산이다.

- `HOUSEHOLD`, `SHARED`는 `owner_member_id`가 없다.
- `PERSONAL`은 current Household의 실제 Member를 `owner_member_id`로 가진다.
- `ME`, `PARTNER` 같은 상대적 식별자는 저장하지 않는다.
- Category Budget은 EXPENSE Category만 새로 연결할 수 있다.
- archived Category에 연결된 기존 Budget은 삭제하거나 숨기지 않고 archive 상태와 함께 표시한다.

## 계산

Budget 사용액은 같은 월·Scope·Category 조건의 순소비다.

```text
사용액 = NORMAL EXPENSE - REFUND EXPENSE
```

TRANSFER와 INCOME은 포함하지 않는다. 삭제 거래는 제외한다.

Scope 전체 Budget의 사용액은 다음 관계를 가진다.

```text
HOUSEHOLD spent = 모든 PERSONAL spent 합 + SHARED spent
PERSONAL(owner) spent = 해당 Owner의 PERSONAL 순소비
SHARED spent = SHARED 순소비
```

`payer_member_id`는 실제 결제자 기록이며 Budget 귀속이나 차감에 사용하지 않는다. 따라서 SHARED 지출은 Payer의 PERSONAL Budget에서 차감되지 않는다.

카드 구매는 EXPENSE이므로 사용액에 포함한다. 카드대금 납부는 TRANSFER이므로 다시 포함하지 않는다. 같은 Household timezone 월 경계와 Scope·Category 조건을 모든 계산에 동일하게 적용한다.

사용액은 Transaction 원장에서 매번 파생한다. Budget row에 사용액을 저장하거나 별도 aggregate table·cache를 두지 않는다.

## 설정과 파생값

- `amount >= 0`이다.
- 각 Scope의 `budgetAmount`는 해당 Budget row의 독립 저장값이다. `HOUSEHOLD` amount를 `PERSONAL` amount 합으로 계산하지 않는다.
- 미설정은 Budget row가 없고 API의 `budgetAmount=null`이다.
- 0원은 실제 Budget row와 `budgetAmount=0`이다.
- `remainingAmount = budgetAmount - spentAmount`이며 초과 시 음수다.
- 사용률은 `budgetAmount > 0`일 때만 `spentAmount / budgetAmount`로 계산한다.
- 초과는 허용하며 Transaction 저장을 막지 않는다.
- Scope 전체 Budget과 Category Budget은 독립 설정이고 합계 일치를 강제하지 않는다.

HOUSEHOLD 사용액은 PERSONAL/SHARED 사용액을 포함하는 상위 관점이다. 같은 거래가 HOUSEHOLD와 해당 PERSONAL 또는 SHARED 카드에 함께 보이는 것은 의도된 중첩이며, 카드들의 사용액을 다시 합산하지 않는다.

## Identity와 동시 수정

Budget identity는 다음 조합이다.

```text
(household_id, budget_month, scope, owner_member_id, category_id)
```

nullable owner/category도 같은 값으로 취급하는 PostgreSQL `UNIQUE NULLS NOT DISTINCT`로 race를 차단한다. 수정과 삭제는 optimistic `version`을 사용하고 stale 요청을 안정적인 `409 BUDGET_VERSION_CONFLICT`로 거부한다.

## V1 규칙

- 월간 예산은 서로 독립적이다.
- 월별 Budget amount는 해당 월 row만 보존한다. 변경 이력 snapshot이나 자동 이월은 없으며 과거 월 사용액도 현재 유효 Transaction 원장에서 다시 계산한다.
- 미사용 금액 자동 이월은 하지 않는다.
- 음수 예산을 허용하지 않는다.
- 전체 예산과 세부 예산이 동시에 있어도 세부 합계가 전체와 같아야 한다고 강제하지 않는다.
- 예산 초과는 거래 저장을 차단하지 않고 경고만 제공한다.

한 Member의 PERSONAL Budget이 미설정이어도 HOUSEHOLD Budget에는 영향이 없다. 반대로 HOUSEHOLD Budget이 미설정이면 모든 PERSONAL Budget이 설정돼 있어도 HOUSEHOLD `budgetAmount`와 `remainingAmount`는 `null`이다.
