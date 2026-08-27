---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - 03-data/transaction-ledger-rules.md
  - 06-security/privacy-model.md
---

# Account 도메인

## Account Type

- `CHECKING`: 입출금 계좌
- `SAVINGS`: 적금·저축 계좌
- `CASH`: 현금
- `CREDIT_CARD`: 신용카드 미결제 부채
- `OTHER`: V1 범위에서 분류되지 않는 잔액 계정

## Nature

- `ASSET`: 잔액 증가가 순자산 증가
- `LIABILITY`: 잔액 증가가 순자산 감소

일반적으로 CREDIT_CARD는 LIABILITY다.

## Ownership

- `PERSONAL`: `owner_member_id` 필수
- `SHARED`: `owner_member_id` 없음

Account 소유권과 Transaction Scope는 독립적이다. 개인 카드로 공동 데이트 비용을 결제할 수 있다.

## 잔액

```text
current_balance = opening_balance + 유효 Account Entry의 balance_delta 합
```

- ASSET 지출: delta 음수
- LIABILITY 카드 사용: delta 양수
- LIABILITY 납부: delta 음수

Slice 2의 현재 잔액 조회는 `opening_balance`와 `deleted_at IS NULL`인 Transaction의 Entry만 합산한다. Entry row는 논리삭제된 Transaction에도 보존하되 잔액에서는 제외한다.

## 저축 표시

`savings_enabled=true`인 ASSET Account를 저축 목적 계좌로 본다. Account 사이 이동을 저축으로 집계할 때 source와 destination의 savings 속성을 함께 본다.

## 데이터 최소화

전체 계좌번호와 카드번호를 저장하지 않는다. 식별이 필요하면 기관명, 별칭, 마지막 네 자리만 저장한다.

## 보관

거래가 연결된 Account는 물리삭제하지 않고 archive한다. archive 이후 새 거래 선택에서는 제외하되 과거 조회와 잔액 검산에는 남긴다.

## Slice 2 계약

- Account는 current Household에 속하고 PERSONAL owner는 같은 HouseholdMember여야 한다.
- `currency` 입력은 `KRW`, `last_four`는 nullable 숫자 4자리다. 전체 계좌번호나 카드번호는 받지 않는다.
- `savings_enabled=true`는 ASSET Account에만 허용한다.
- Account type/nature는 reference data로 CREDIT_CARD/LIABILITY를 표현할 수 있지만 Slice 2 Transaction posting은 active ASSET에만 허용한다. CREDIT_CARD는 nature와 무관하게 이 Slice에서 거부한다.
- 목록은 active-only가 기본이고 `includeArchived=true`일 때 보관 Account를 함께 반환한다.
