---
status: active
version: 1.0
last_updated: 2026-08-29
related:
  - 02-domain/account.md
  - 02-domain/financial-metrics.md
  - 04-api/api-conventions.md
  - 05-frontend/information-architecture.md
---

# 자산 화면

Assets는 `?screen=assets&view=all`에서 시작하는 실제 하단 destination이다. current Household 원장에서 파생한 값을 표시하며 별도 입력·aggregate를 만들지 않는다.

## URL과 상태

- 전체: `?screen=assets&view=all`
- 개인: `?screen=assets&view=personal&memberId={actualMemberId}`
- 공동: `?screen=assets&view=shared`

잘못된 view, foreign/nonexistent Member ID, 불필요한 parameter는 전체 canonical URL로 fail closed 한다. 선택 변경은 history entry를 만들고 direct load, refresh, back/forward에서 동일한 filter를 복원한다.

loading 중에는 이전 금융 숫자를 남기지 않는다. API 오류는 안정적인 설명과 `다시 불러오기` action을 제공한다. Account가 없어도 zero summary와 12개 추이를 유지하고 첫 Account 생성 경로를 안내한다. 선택한 소유 기준에 Account가 없으면 전체 empty와 구분한다.

## Household 상단 지표

- 총자산
- 총부채
- 순자산

세 값은 소유 filter와 무관한 Household 전체다. signed 원장 값을 그대로 표시하고 음수 ASSET·LIABILITY나 0원을 숨기거나 clamp하지 않는다.

## 월별 추이

직전 11개 완료 월말과 현재 한 점의 Household 자산·부채·순자산을 표시한다. 마지막 점은 `진행 중`과 `현재` 의미를 함께 제공한다. 시각적 SVG는 설명 가능한 이름을 갖고 같은 12개 값을 semantic table로도 제공한다.

추이는 소유 filter와 무관하게 Household 전체다. 과거 거래 수정·삭제 시 다음 조회 결과를 그대로 다시 표시하며 client cache에서 과거 값을 조작하지 않는다.

## 소유 filter와 현재 소계

```text
전체 | 실제 Member A | 실제 Member B | 공동
```

실제 Member는 `/api/v1/assets`가 반환한 ID와 display name을 사용한다. 선택 시 현재 자산·부채·순자산 소계와 Account 목록만 바뀐다. 개인은 Account owner, 공동은 Account ownership 기준이며 Transaction Scope로 귀속을 추론하지 않는다.

## Account 그룹

- `ASSET Account`
- `LIABILITY Account`

각 Account는 name, current balance, type 또는 institution, 개인 owner 또는 공동, savings, archive 상태를 표시한다. active와 archived, 양수·0·음수 Account를 모두 유지한다. 전체 계좌번호와 `lastFour`는 표시하지 않는다.

정렬은 backend canonical 순서를 보존한다. nature는 ASSET 뒤 LIABILITY이며 PERSONAL은 actual Member 순서, SHARED는 그 뒤이고 같은 bucket에서는 sort order와 ID가 안정 순서를 결정한다.

## Account 관리와 빠른 입력

`Account 관리 열기`는 기존 Settings Sheet를 사용한다. 닫으면 Assets의 호출 button으로 focus를 복귀시킨다. 생성·수정·보관 form을 Assets 화면에 복제하지 않는다.

Paw FAB는 Household timezone 오늘 날짜로 기존 Quick Entry를 연다. Calendar, Budget, Statistics, Assets 이동과 현재 destination의 `aria-current=page`를 유지한다.

## 접근성·반응형

- filter button은 선택 상태를 `aria-pressed`로 전달한다.
- 추이 SVG와 table은 같은 금융 의미를 제공한다.
- 금액의 부호와 Account nature label을 text로 제공한다.
- loading/error/empty 상태는 `status` 또는 `alert`로 노출한다.
- mobile 한 열을 기본으로 하고 넓은 화면에서는 summary·Account 정보를 읽기 쉬운 grid로 확장한다.
- reduced motion에서는 새 장식 animation을 사용하지 않는다.

Goal card와 Goal 상세는 Calendar/Goal 흐름이 소유한다. Goal link, target, contribution/projection을 Assets에 병합하거나 current Account balance에 다시 더하지 않는다.
