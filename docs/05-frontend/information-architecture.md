---
status: active
version: 1.1
last_updated: 2026-08-29
related:
  - 01-product/benchmark-weple-money.md
  - 05-frontend/calendar-screen.md
  - 05-frontend/recurring-transactions.md
  - 05-frontend/quick-entry.md
  - 05-frontend/marriage-goal.md
  - 05-frontend/assets-screen.md
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

이 문서들의 `active` 상태는 현재 디자인 계약이라는 뜻이다. Calendar Home과 Quick Entry Sheet는 Slice 4, Budget destination은 Slice 5, Marriage Goal 실제 지표·상세는 Slice 8, Assets destination은 Slice 9에서 활성화됐다. production illustration은 별도 asset 범위다.

## 하단 탐색

```text
달력 | 예산 | + | 통계 | 자산
```

- `+`는 탭이 아니라 빠른 입력을 여는 주요 action이다.
- Bottom Navigation과 중앙 Paw FAB는 viewport 하단에 고정하고 본문에는 safe-area와 겹치지 않는 여백을 둔다.
- 설정은 상단 프로필 또는 더보기 메뉴에 둔다.
- 결혼자금은 Calendar Home 요약 카드에서 상세로 접근한다. Slice 8은 새 하단 tab이나 Assets 화면을 만들지 않는다.
- Calendar, Budget, Statistics, Assets는 실제 destination이며 현재 화면 button에 `aria-current=page`를 적용한다.
- Calendar 외 destination의 Paw FAB는 Household timezone 오늘 날짜 Quick Entry를 연다.

## 달력 중심 Home

메인 화면은 Couple identity, 월 소비 요약, 결혼자금 hero, Scope filter, 달력, 선택일 거래 목록을 하나의 자연스러운 세로 흐름에 제공한다. 별도의 복잡한 dashboard 탭이나 nested vertical scroll을 만들지 않는다. 세부 계약은 [Home/달력 화면](calendar-screen.md)을 따른다.

## Budget 화면

Budget은 같은 Couple header와 하단 탐색을 유지하고 월 이동, HOUSEHOLD/실제 Member PERSONAL/SHARED 기본 카드, 사용자 설정 Category Budget을 세로 흐름으로 제공한다. 생성·수정·삭제와 사용 내역은 Bottom Sheet로 progressive disclosure한다. 세부 계약은 [예산 화면](budget-screen.md)을 따른다.

## Statistics 화면

Statistics는 같은 Couple header와 하단 탐색을 유지하고 기간, 실제 Member/공동 Scope, summary, comparison, monthly trend, Category/subject/Account breakdown을 하나의 vertical scroll로 제공한다. 주요 숫자는 Bottom Sheet에서 원장을 on-demand 조회하며 저축만 전용 savings activity read model을 사용한다. 세부 계약은 [통계 화면](statistics-screen.md)을 따른다.

## Assets 화면

Assets는 같은 Couple header와 하단 탐색을 유지하고 Household 순자산 hero, 고정 Household 월 추이, actual Member/공동 소유 filter, 선택 소계, ASSET/LIABILITY Account 목록을 하나의 vertical scroll로 제공한다. Account 생성·수정·보관은 중복 UI를 만들지 않고 기존 Settings로 이동한다. 세부 계약은 [자산 화면](assets-screen.md)을 따른다.

## 반복 거래 설정

반복 거래는 새 하단 탭을 만들지 않고 설정 Sheet 안의 독립 section으로 제공한다. active, paused, ended 규칙을 함께 보여 주고 생성·수정·일시정지·재개를 nested Sheet에서 처리한다. 재개 시 일시정지 기간을 소급 생성하지 않는다는 점을 action 근처에 명시한다. Calendar 선택일 거래, Budget 사용 내역, Statistics drill-down과 저축 활동에서 자동 생성된 거래는 `반복` text badge로 provenance를 표시한다. 세부 계약은 [반복 거래 설정](recurring-transactions.md)을 따른다.

## 데이터 내보내기

CSV는 새 하단 destination을 만들지 않고 Settings Sheet 안의 `데이터 내보내기` section에서 제공한다. 시작일과 종료일의 기본값은 Household timezone 현재 월 1일부터 오늘이며, 사용자가 수정한 값은 오류 뒤에도 유지한다.

pending, JSON/network 오류, 성공을 text `status`/`alert`로 표시한다. 성공하면 browser download를 시작하지만 Settings를 닫거나 keyboard focus를 body로 이동하지 않는다. 설명에는 current Household의 유효 거래, 논리삭제 제외, 운영 backup 대체 불가를 함께 명시한다. 세부 형식은 [CSV 거래 내보내기](../04-api/csv-export.md)를 따른다.

## Marriage Goal 상세

Calendar Home은 Goal 없음이면 생성 CTA, Goal 존재면 실제 current/target/rate/이번 달 순저축 card를 표시한다. card는 `?screen=goal` 상세로 이동하고 새로고침/back/forward를 지원한다.

상세는 hero, current/target/rate/remaining, 이번 달/최근 평균/projection, accessible 6개월 추세, 연결 Account, 최근 Transfer 근거를 순서대로 제공한다. 생성·수정·연결은 Bottom Sheet, 연결 해제는 Account row의 확인 단계로 처리한다. Goal용 수동 기여금 action은 제공하지 않는다.

## 전역 필터

가능한 화면에서 동일한 의미로 사용한다.

```text
전체 | 실제 Member A | 실제 Member B | 공동
```

개인 항목은 API가 반환한 실제 Member 이름을 사용한다. `ME`나 `PARTNER`를 data model에 추가하지 않는다. 선택값은 달력·예산·통계의 조회 조건과 Assets Account ownership filter에 반영하되 화면별로 부적절한 경우 명확히 비활성화한다. Assets의 월 추이는 현재 소유 filter와 무관하게 Household 전체를 유지한다.

## 반응형

- 모바일을 기본으로 설계
- 데스크톱에서는 콘텐츠 폭을 제한하고 달력·상세 패널을 나란히 배치 가능
- 터치 target 최소 크기와 keyboard 탐색 지원

## Progressive Disclosure

일반 사용 흐름에는 핵심 정보만 보이고, 상세 필터·반복·고급 날짜·메모는 추가 조작으로 연다.
