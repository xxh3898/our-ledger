---
status: active
version: 0.1
last_updated: 2026-08-27
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

## Account 잔액

```text
opening_balance + 유효 entry.balance_delta 합
```

LIABILITY 잔액은 양수 부채로 표현한다.

## 순자산

```text
ASSET 잔액 합 - LIABILITY 잔액 합
```

## 무지출일

해당 날짜 순소비가 0이면 무지출일이다. TRANSFER는 무시한다. 환불만 있는 날도 순소비가 음수가 될 수 있으므로 UI에서는 “무지출” 표시와 환불 표시를 함께 검토한다.

## 전월 비교

```text
(이번 달 - 지난 달) / 지난 달 * 100
```

지난 달이 0이면 증감률은 `null`, 금액 차이만 제공한다.

## 예상 Goal 달성일

최근 3개월 이상의 확정 월 순저축 평균을 기본값으로 사용한다. 남은 금액이 0 이하면 달성 상태다. 평균이 0 이하이면 예상일은 없다.
