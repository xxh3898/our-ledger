---
status: active
version: 0.5
last_updated: 2026-08-29
related:
  - 07-quality/financial-invariants.md
---

# 재무 지표 정의

모든 지표는 Household timezone과 유효 Transaction 기준으로 계산한다. `deleted_at`이 있는 거래는 제외한다.

## 총수입

```text
NORMAL INCOME 합계
```

V1에서 INCOME 환불은 모델링하지 않는다. 정정은 원 거래 수정·삭제로 처리한다.

## 순소비

```text
NORMAL EXPENSE 합계 - REFUND EXPENSE 합계
```

개인·공동·Category·Account 필터를 동일하게 적용한다.

REFUND는 원 NORMAL EXPENSE의 Scope, Owner, Payer, Category와 PRIMARY Account를 상속하므로 원 지출과 같은 bucket에서 차감된다. active Refund만 포함하고 logical delete된 Refund는 제외한다.

## 개인 소비

```text
EXPENSE AND scope=PERSONAL AND owner_member_id=선택 Member
```

## 공동 소비

```text
EXPENSE AND scope=SHARED
```

## 저축액

V1 기본 계산은 다음 순증가 이체다.

```text
source.savings_enabled=false
AND destination.savings_enabled=true
인 TRANSFER의 destination 증가액
-
반대 방향의 인출액
```

저축계좌끼리의 이동은 0이다. 소비로 인해 저축계좌 잔액이 감소한 것은 저축 취소가 아니라 자금 사용으로 별도 표시한다.

## 저축률

```text
저축액 / 총수입 * 100
```

총수입이 0이면 `null`이다. 0%로 표시하지 않는다.

Statistics API의 저축률과 증감률은 소수점 한 자리에서 `HALF_UP` 반올림한다. 이전 기간 금액이 0이면 percent change는 `null`이며 금액 차이는 유지한다. 저축률 비교는 percent change가 아니라 percentage point 차이다.

TRANSFER에는 Scope가 없으므로 V1 Statistics의 저축액과 저축률은 ALL에서만 계산한다. PERSONAL/SHARED에서는 Account ownership으로 귀속을 추론하지 않고 `null`로 제공한다.

## Account 잔액

```text
opening_balance + 유효 entry.balance_delta 합
```

LIABILITY 잔액은 양수 부채로 표현한다.

ASSET EXPENSE Refund는 positive delta, CREDIT_CARD/LIABILITY EXPENSE Refund는 negative delta다. Refund 삭제 시 해당 Entry는 원장에 남더라도 연결 Transaction이 삭제 상태이므로 잔액 합에서 제외된다.

Assets read model은 active와 archived Account를 모두 포함한다. Account archive는 이후 posting만 막는 lifecycle 상태이며 기존 opening balance와 유효 Entry를 자산 상태에서 제거하지 않는다. 현재 Account row는 `openingBalance`, `ledgerDelta`, `currentBalance`를 함께 제공하되 전체 계좌번호나 `lastFour`는 노출하지 않는다.

## 순자산

```text
ASSET 잔액 합 - LIABILITY 잔액 합
```

총자산과 총부채는 각 nature Account의 실제 signed balance 합이다. 음수 ASSET 또는 과납 등 음수 LIABILITY를 0으로 clamp하지 않는다. PERSONAL 소계는 Account의 actual owner Member, 공동 소계는 `ownership=SHARED`를 기준으로 하며 거래 Scope와 무관하다. Household 순자산은 모든 Member와 공동 순자산의 합과 일치한다.

## 자산 월 추이

Assets는 Household timezone의 직전 11개 완료 calendar month 말과 현재 calendar month의 실제 현재 시점을 반환한다.

```text
완료 월말 Account 잔액 = opening_balance + 해당 월말까지의 유효 entry.balance_delta
현재 점 = 현재 Account 잔액의 Household 합계
```

Account의 `opening_balance_as_of`가 해당 월말보다 뒤면 그 월 기여도는 0이다. logical delete Transaction은 모든 점에서 제외하고, archived Account와 반복거래가 생성한 canonical Transaction은 포함한다. 과거 거래 수정·삭제 시 persisted aggregate를 보정하는 대신 다음 조회에서 원장을 다시 계산한다. Goal Account link/unlink와 `starting_balance` snapshot은 Account 원장을 바꾸지 않으므로 Assets 값에 가산하지 않는다.

## 무지출일

해당 날짜 순소비가 0이면 무지출일이다. TRANSFER는 무시한다. 환불만 있는 날도 순소비가 음수가 될 수 있으므로 UI에서는 “무지출” 표시와 환불 표시를 함께 검토한다.

## 전월 비교

```text
(이번 달 - 지난 달) / 지난 달 * 100
```

지난 달이 0이면 증감률은 `null`, 금액 차이만 제공한다.

## 예상 Goal 달성일

Goal 지표의 저축 경계는 Household Statistics의 `savings_enabled` 경계와 다르다. 현재 연결과 Account별 `linked_at`이 발생 시점에 유효한 TRANSFER에 대해 비Goal→Goal은 양수, Goal→비Goal은 음수, Goal 내부 이동은 0이다. INCOME/EXPENSE/REFUND는 현재 잔액에는 반영하지만 Goal 순저축에는 포함하지 않는다.

월별 추이는 Household timezone의 현재 월 포함 최근 6개월을 빈 월 0 row까지 반환한다. 이번 달은 현재 calendar month 전체의 유효 occurrence를 사용하며 현재 시각 이후로 입력된 같은 월 거래를 임의 제거하지 않는다.

최근 평균은 current partial month를 제외한 직전 3개 완료 월의 순저축 합을 `floorDiv(sum, 3)`으로 정수화한다. 세 월 각각에 현재 Goal Account 연결이 월 종료 전에 한 번이라도 유효해야 하며 그렇지 않으면 표본 부족 `null`이다. 음수 합의 정수화도 바닥 방향이므로 예상일을 낙관적으로 앞당기지 않는다.

```text
remaining = max(targetAmount - currentAmount, 0)
months = ceil(remaining / recentAverageMonthlySavingsAmount)
expectedAchievementMonth = current Household month + months
```

- `ACHIEVED`: remaining이 0이며 예상 월은 null
- `INSUFFICIENT_HISTORY`: 완료 월 표본이 3개 미만
- `NON_POSITIVE_AVERAGE`: 평균이 0 이하
- `PROJECTED`: 평균이 양수이며 `expectedAchievementMonth` 제공
