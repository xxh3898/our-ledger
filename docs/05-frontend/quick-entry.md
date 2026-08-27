---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 01-product/user-flows.md
  - 02-domain/transaction.md
---

# 빠른 입력

## 목표

일반 지출은 한 화면에서 최소 입력으로 저장한다.

## 기본 순서

1. `지출 / 수입 / 이체`
2. 금액
3. `치호 / 여자친구 / 공동`
4. Category
5. Account
6. 날짜
7. 저장

지출에서는 필요 시 Payer를 확인한다. 수입에서는 Owner 또는 Shared 범위를 선택한다. 이체에서는 source와 destination을 선택하고 Scope/Category를 숨긴다.

## 기본값

- 날짜: 오늘
- 통화: KRW
- Account: 최근 사용값 또는 사용자 기본값
- Scope: 최근값을 무조건 재사용해 오입력을 유발하지 않도록 명확히 표시

## 고급 옵션

- 메모
- 정확한 시간
- 반복 설정
- 환불은 원 거래 상세에서 진입

## 유효성

- 금액은 1원 이상
- source와 destination 동일 금지
- 개인 거래 Owner 필수
- shared 거래 Owner 없음
- Category type 일치
- archive된 Account/Category 신규 선택 금지

## 저장 후

성공 시 현재 화면으로 돌아가고 달력·예산·자산 관련 query를 갱신한다. 중복 submit을 막고 실패 시 입력값을 유지한다.
