---
status: active
version: 0.3
last_updated: 2026-08-28
related:
  - ADR-002
  - 02-domain/account.md
---

# 거래 원장 규칙

`our-ledger`는 완전한 복식부기 회계시스템을 목표로 하지 않지만, Transaction과 Account Entry를 분리해 카드와 이체를 일관되게 처리한다.

## Entry 의미

`balance_delta`는 해당 Account 화면에서 보이는 잔액 변화다.

| 사건 | Account | Nature | delta |
|---|---|---|---:|
| 월급 수입 | 입출금 | ASSET | +2,500,000 |
| 통장 지출 | 입출금 | ASSET | -12,000 |
| 카드 지출 | 신용카드 | LIABILITY | +12,000 |
| 통장→적금 | 통장 | ASSET | -1,000,000 |
| 통장→적금 | 적금 | ASSET | +1,000,000 |
| 카드대금 납부 | 통장 | ASSET | -650,000 |
| 카드대금 납부 | 신용카드 | LIABILITY | -650,000 |
| 카드 환불 | 신용카드 | LIABILITY | -20,000 |

## 거래별 Entry 수

### INCOME

- Entry 1개
- 대상 Account가 일반 ASSET이면 `+amount`
- V1에서는 LIABILITY로 직접 들어오는 INCOME 입력을 허용하지 않는다.

### EXPENSE NORMAL

- Entry 1개
- ASSET 결제: `-amount`
- LIABILITY 결제: `+amount`

### EXPENSE REFUND

- Entry 1개
- 원 지출의 계좌 효과를 반대로 적용
- ASSET 환불: `+amount`
- LIABILITY 환불: `-amount`

### TRANSFER

- `SOURCE` 1개, `DESTINATION` 1개
- ASSET source: 음수
- ASSET destination: 양수
- LIABILITY destination 납부: 음수
- 같은 Account를 source와 destination으로 사용할 수 없다.

## 저장 원자성

Transaction과 모든 Entry는 하나의 DB transaction에서 저장한다. 일부 Entry만 저장된 상태가 발생하면 안 된다.

## 수정

거래 수정 시 기존 Entry를 임의 누적하지 않는다. 계산된 expected entry set으로 교체하거나 명확한 갱신 전략을 사용하고, 변경 전후 잔액 회귀를 테스트한다.

Slice 3는 기존 Entry set을 제거한 뒤 계산한 expected Entry set을 다시 저장한다. 이전 delta를 새 delta에 더하지 않으며 `(transaction_id, entry_role)` unique가 역할 중복을 차단한다.

## Slice 3 실행 범위

- INCOME: active ASSET Account에 PRIMARY 1개, `balance_delta=+amount`
- EXPENSE NORMAL: active ASSET Account에 PRIMARY 1개, `balance_delta=-amount`
- CREDIT_CARD/LIABILITY EXPENSE NORMAL: PRIMARY 1개, `balance_delta=+amount`
- ASSET→ASSET TRANSFER: SOURCE `-amount`, DESTINATION `+amount`
- ASSET→LIABILITY TRANSFER: SOURCE `-amount`, DESTINATION `-amount`
- LIABILITY source와 REFUND는 후속 Slice까지 생성하지 않는다.
- Transaction과 Entry insert/update는 하나의 Spring transaction이다. 참조 검증이 실패하면 Transaction과 모든 Entry가 남지 않는다.
- 논리삭제는 Transaction의 `deleted_at/deleted_by`를 기록하고 Entry는 검산 근거로 보존한다. 잔액 query는 삭제된 Transaction의 Entry를 제외한다.
