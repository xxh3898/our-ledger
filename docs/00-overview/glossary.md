---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 02-domain/transaction.md
  - 03-data/transaction-ledger-rules.md
---

# 용어집

| 용어 | 의미 |
|---|---|
| Household | 두 사용자의 재무 데이터가 속하는 최상위 경계 |
| Member | Household에 참여한 사용자 |
| Account | 현금, 입출금, 저축, 신용카드 등 잔액을 추적하는 수단 |
| ASSET | 현금성 자산처럼 잔액이 증가할수록 순자산이 증가하는 계좌 성격 |
| LIABILITY | 신용카드 미결제액처럼 잔액이 증가할수록 순자산이 감소하는 계좌 성격 |
| Transaction | 수입·지출·이체라는 경제 사건 |
| Account Entry | 거래가 특정 계좌 잔액에 만든 변화 |
| INCOME | 소비가 아닌 자금 유입 |
| EXPENSE | 소비 발생. `NORMAL` 또는 `REFUND` 조정 유형을 가짐 |
| TRANSFER | 계좌 사이 자금 이동. 수입·소비에 포함하지 않음 |
| Scope | 거래의 소비·수입 귀속 범위인 `PERSONAL` 또는 `SHARED` |
| Owner | 개인 거래가 누구의 수입·소비인지 나타내는 Member |
| Payer | 지출을 실제로 결제한 Member. 정산 계산에는 사용하지 않음 |
| NORMAL | 일반 수입·지출 |
| REFUND | 기존 지출을 상쇄하는 환불 거래 |
| Category Group | 카테고리를 묶는 사용자 정의 그룹 |
| Budget | 특정 월과 범위·카테고리에 설정한 소비 한도 |
| Recurring Transaction | 주기에 따라 실제 Transaction을 생성하는 규칙 |
| Goal | 결혼자금 같은 장기 재무 목표 |
| Goal Account | Goal의 현재 금액을 계산하는 데 연결된 실제 Account |
| 저축계좌 | `savings_enabled=true`인 자산 계좌 |
| 현재 보유금 | Goal에 연결된 계좌의 현재 유효 잔액 합계 |
| 누적 마련금 | 연결 당시 시작금액과 외부에서 Goal 계좌로 유입된 순저축 합계 |
| 무지출일 | 해당 날짜의 순소비가 0인 날. 이체는 무시 |
| 논리삭제 | 거래를 물리 제거하지 않고 `deleted_at`으로 제외하는 방식 |
| 재무 불변식 | 구현 변경 후에도 반드시 유지되어야 하는 계산 규칙 |
