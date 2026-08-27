---
status: active
version: 0.2
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

## Slice 2 화면

- 현재 Household의 Account를 이름, type, PERSONAL/SHARED owner, 기초 잔액·기준일로 생성하고 active 목록에서 archive할 수 있다.
- Category Group과 Category를 지출/수입 type으로 생성하고 active 목록에서 archive할 수 있다. Group 없는 Category를 허용한다.
- 빠른 입력은 지출/수입, 양수 금액, PERSONAL/SHARED, Owner, optional Payer, type-matching Category, active ASSET Account, 날짜, optional memo를 받는다.
- 최근 목록은 `occurredAt DESC, id DESC`의 API 순서를 그대로 표시하고 edit/delete를 제공한다. edit/delete는 조회한 `version`을 사용한다.
- mutation helper는 same-origin `XSRF-TOKEN` cookie를 `X-XSRF-TOKEN` header로 보낸다. pending 동안 해당 submit/delete button을 비활성화한다.
- 서버 validation/domain 실패 시 Account/Category/Transaction form state를 초기화하지 않고 error message를 `role=alert`로 표시한다.

TRANSFER 선택, Calendar/Home 정보 구조, 최종 캐릭터·색상 asset은 이 Slice 화면에서 제외한다.
