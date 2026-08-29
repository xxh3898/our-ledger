---
status: active
version: 0.3
last_updated: 2026-08-29
related:
  - 02-domain/financial-metrics.md
---

# 통계 화면

## 구현 범위

- 수입
- 순소비
- 저축
- 저축률
- Category별
- 개인·공동별
- PRIMARY Account별
- 월별 추이
- 명시적 이전 기간 비교

## 기간

이번 달, 지난달, 최근 3개월, 최근 6개월, 1년, 직접 선택.

- 이번 달/지난달은 바로 이전 calendar month와 비교한다.
- 최근 3/6/12개월은 바로 앞의 같은 개수 calendar month와 비교한다.
- 직접 선택은 바로 앞의 같은 inclusive day count와 비교한다.
- 기본값은 Household timezone의 이번 달과 ALL이다.

## 원칙

- backend 계산을 기준으로 한다.
- frontend가 별도 합계를 재구성해 다른 숫자를 만들지 않는다.
- 모든 주요 숫자는 해당 조건 거래 목록 또는 savings activity로 이동 가능해야 한다.
- 지난 기간 값이 0이면 잘못된 무한대 증감률을 표시하지 않는다.
- 금액 차이를 percent보다 먼저 표시하고 증가·감소·변화 없음을 text로 함께 제공한다.
- income 0 저축률과 previous 0 percent는 `계산 불가`로 표시한다.

## Scope

```text
전체 | 실제 Member A | 실제 Member B | 공동
```

Calendar와 같은 실제 Household Member ID/name을 사용한다. PERSONAL/SHARED 선택에서는 Transfer를 Account ownership으로 귀속하지 않으며 저축·저축률 대신 다음 설명을 표시한다.

```text
저축은 Account 간 이체 기준이라 전체 보기에서 확인할 수 있어요.
```

조건 변경 pending 중 이전 조건의 숫자를 새 조건 결과처럼 유지하지 않는다.

## 화면 순서

모바일의 하나의 natural vertical scroll에서 다음 순서를 유지한다.

```text
통계 제목
기간 preset/custom
전체/Member/공동
이번 기간 요약
이전 기간 비교
월별 추이
Category별 순소비
주체별 순소비
Account별 순소비
```

월별 추이는 빈 달과 actual amount를 읽을 수 있는 semantic table로 표시한다. Category와 Account는 archived 상태를 text로 유지하며 Category share가 계산 불가인 경우 색상이나 bar로 의미를 꾸며내지 않는다.

## 시각화

차트보다 숫자와 비교 가능한 표/list를 우선한다. 새 chart dependency를 추가하지 않는다. 모바일에서 넓은 표는 화면 전체가 아니라 표 container만 horizontal overflow를 허용하고 label·실제 금액·상태 text를 유지한다. production illustration은 이 Slice 범위가 아니다.

## URL과 history

```text
?screen=statistics&preset=this-month&view=all
?screen=statistics&preset=recent-3-months&view=member&memberId=100
?screen=statistics&preset=custom&from=2026-06-15&to=2026-08-20&view=shared
```

Router dependency 없이 `history.pushState/replaceState`와 `popstate`를 사용한다. invalid preset/date/range는 이번 달로, invalid/foreign Member는 ALL로 각 상태를 안전하게 정규화한다. comparison query는 canonical current state에서 파생한다.

## Drill-down Sheet

- 수입/순소비/Category/Account/주체는 기존 Transaction API를 on-demand 조회한다.
- 저축은 impact 0 Transfer를 제외한 Statistics savings activity API를 조회한다.
- REFUND는 `환불`, `+금액`으로 표시한다.
- Sheet open 시 닫기 button으로 focus를 이동하고 Escape/backdrop/close를 지원한다.
- 닫은 뒤 실제 opener로 focus를 돌려준다.

## 하단 탐색과 Paw FAB

Calendar, Budget, Statistics, Assets는 실제 destination이고 Statistics button에 현재 화면이면 `aria-current=page`를 적용한다. Statistics Paw FAB는 보이지 않는 Calendar 선택일이 아니라 Household timezone 오늘 날짜로 Quick Entry를 연다.
