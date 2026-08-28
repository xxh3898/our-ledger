---
status: active
version: 0.7
last_updated: 2026-08-28
related:
  - 01-product/benchmark-weple-money.md
  - 05-frontend/calendar-screen.md
  - 05-frontend/quick-entry.md
  - 05-frontend/marriage-goal.md
  - 05-frontend/design-system.md
  - 05-frontend/interaction-motion.md
  - 06-security/authentication.md
---

# 정보구조

## Auth/Household 진입 상태

Ledger 본 화면 전에는 same-origin `/api/v1/me`로 current identity를 확인한다.

- loading: User와 Household 확인 중임을 표시한다.
- success: 표시명, email, Household 이름과 `OWNER`/`MEMBER` role을 표시한다.
- 401: Cloudflare Access 인증이 필요함을 안내하되 app 자체 로그인/OTP form은 만들지 않는다.
- 403: 내부 User 미등록·비활성 또는 Household membership 문제를 안내한다.
- network/server error: 재시도 가능한 일반 오류로 표시한다.

이 상태 화면은 Slice 1에서 확정한 경계를 유지한다. success일 때만 Calendar Home을 로드하고 401/403/error에서는 Ledger request를 시작하지 않는다.

## Slice 3 Transfer/Card Ledger 보존 기능

Slice 4 Calendar Home에서도 다음 기능을 Quick Entry, 선택일 목록, 설정 Sheet로 보존한다.

1. Account 생성·active 목록·archive
2. Category Group/Category 생성·active 목록·archive
3. INCOME/EXPENSE/TRANSFER NORMAL 빠른 입력과 CREDIT_CARD/LIABILITY posting
4. 선택일 거래 목록·수정·논리삭제

기존 current ASSET 잔액 panel은 Calendar Home의 월 소비 hero로 대체한다. Account 잔액과 posting 계산 계약 자체는 바꾸지 않는다.

## Couple-first 디자인 계약

Issue #8에서 확정한 Couple-first 방향은 다음 문서가 나누어 소유한다.

| 문서 | 소유하는 계약 | 실제 구현 시점 |
|---|---|---|
| [Home/달력](calendar-screen.md) | 한 페이지 흐름, 월 요약, 결혼자금 hero, 달력, 선택일 거래, 하단 탐색 | Slice 4 |
| [빠른 입력](quick-entry.md) | 거래 유형별 field, Category·Account·날짜 picker, 저장 상태 | 각 거래 Slice |
| [결혼자금 상세](marriage-goal.md) | Account 기반 목표 지표, 상세 화면, milestone | Slice 8 |
| [Couple-first 디자인 시스템](design-system.md) | 색상, 고양이 정체성, Concept Mockup 사용 경계 | 해당 화면 Slice |
| [Motion과 상호작용](interaction-motion.md) | 전환, feedback, reduced motion | 해당 화면 Slice |

이 문서들의 `active` 상태는 현재 디자인 계약이라는 뜻이다. Calendar Home과 Quick Entry Sheet는 Slice 4, Budget destination은 Slice 5에서 활성화됐다. Marriage Goal 실제 지표·상세는 Slice 8, production illustration은 별도 asset 범위다.

## 하단 탐색

```text
달력 | 예산 | + | 통계 | 자산
```

- `+`는 탭이 아니라 빠른 입력을 여는 주요 action이다.
- Bottom Navigation과 중앙 Paw FAB는 viewport 하단에 고정하고 본문에는 safe-area와 겹치지 않는 여백을 둔다.
- 설정은 상단 프로필 또는 더보기 메뉴에 둔다.
- 결혼자금은 달력 요약 카드와 자산 화면에서 접근한다.
- Calendar와 Budget은 실제 destination이며 현재 화면 button에 `aria-current=page`를 적용한다.
- Statistics와 Assets는 구현 Slice 전까지 disabled 상태와 `준비 중` text를 유지한다.
- Budget의 Paw FAB는 Household timezone 오늘 날짜 Quick Entry를 연다.

## 달력 중심 Home

메인 화면은 Couple identity, 월 소비 요약, 결혼자금 hero, Scope filter, 달력, 선택일 거래 목록을 하나의 자연스러운 세로 흐름에 제공한다. 별도의 복잡한 dashboard 탭이나 nested vertical scroll을 만들지 않는다. 세부 계약은 [Home/달력 화면](calendar-screen.md)을 따른다.

## Budget 화면

Budget은 같은 Couple header와 하단 탐색을 유지하고 월 이동, HOUSEHOLD/실제 Member PERSONAL/SHARED 기본 카드, 사용자 설정 Category Budget을 세로 흐름으로 제공한다. 생성·수정·삭제와 사용 내역은 Bottom Sheet로 progressive disclosure한다. 세부 계약은 [예산 화면](budget-screen.md)을 따른다.

## 전역 필터

가능한 화면에서 동일한 의미로 사용한다.

```text
전체 | 실제 Member A | 실제 Member B | 공동
```

개인 항목은 API가 반환한 실제 Member 이름을 사용한다. `ME`나 `PARTNER`를 data model에 추가하지 않는다. 선택값은 달력·예산·통계의 조회 조건에 반영하되 화면별로 부적절한 경우 명확히 비활성화한다.

## 반응형

- 모바일을 기본으로 설계
- 데스크톱에서는 콘텐츠 폭을 제한하고 달력·상세 패널을 나란히 배치 가능
- 터치 target 최소 크기와 keyboard 탐색 지원

## Progressive Disclosure

일반 사용 흐름에는 핵심 정보만 보이고, 상세 필터·반복·고급 날짜·메모는 추가 조작으로 연다.
