---
status: active
version: 0.1
last_updated: 2026-08-28
related:
  - 02-domain/goal.md
  - 02-domain/financial-metrics.md
  - 05-frontend/calendar-screen.md
  - 05-frontend/design-system.md
  - 05-frontend/interaction-motion.md
  - 09-decisions/ADR-006-goal-account-model.md
---

# Marriage Goal 상세

## 상태와 원칙

이 문서는 Slice 8에서 구현할 Marriage Goal 상세 화면의 활성 디자인 계약이다. 현재 Goal 기능이 production에 구현됐다는 뜻은 아니다.

- Home보다 감성 비중을 조금 높일 수 있지만 금액과 계산 근거를 우선한다.
- 현재 금액과 저축은 연결된 실제 Account와 Transaction에서 계산한다.
- Goal 금액을 별도로 입력해 자산을 이중 집계하지 않는다.
- 계산 의미는 [Goal 도메인](../02-domain/goal.md), [재무 지표](../02-domain/financial-metrics.md), [ADR-006](../09-decisions/ADR-006-goal-account-model.md)이 최종 authority다.
- [Concept Mockup v1](assets/concept-mockup-v1.png)은 시각 참고이며 pixel 단위 구현 계약이 아니다.

## 화면 구성

1. 두 고양이와 집을 사용한 hero
2. Goal 이름과 현재/목표 금액
3. 달성률 progress
4. 남은 금액
5. 이번 달 저축
6. 최근 월평균 저축
7. 예상 달성일
8. 월별 추이 line chart 하나
9. 연결된 저축 Account
10. 최근 저축 내역

```text
우리 집까지

32,400,000원
/ 100,000,000원

두 고양이 ━━━━━━━━━○──────── 집
32.4%

67,600,000원 남았어요
이번 달 +1,800,000원
예상 달성 2029년 4월

[월별 추이 line chart]

연결된 저축 Account
- 공동 결혼통장
- 개인 적금
```

표시된 이름과 금액은 구조를 설명하는 sample이며 고정값이나 실제 사용자 data가 아니다.

## 지표 표시

- 현재/목표 금액과 달성률을 함께 표시해 progress graphic만으로 수치를 추론하게 하지 않는다.
- 남은 금액은 목표액과 현재 보유금의 관계를 명확한 문장으로 보여 준다.
- 이번 달 저축과 최근 월평균은 같은 집계 기준을 사용하고 기간을 알 수 있게 한다.
- 예상 달성일은 월평균 순저축이 0 이하이거나 표본이 부족하면 임의 날짜를 표시하지 않고 계산 불가 이유를 안내한다.
- 월별 추이는 한 개의 line chart로 제한하고 point의 월과 금액을 text 또는 접근 가능한 설명으로 확인할 수 있게 한다.
- 저축계좌 사이 이동을 신규 저축으로 중복 집계하지 않는다.

## Account와 최근 저축

- 연결된 Account는 실제 Account 이름과 ownership을 표시한다.
- inactive 또는 연결 해제된 Account의 처리와 과거 지표 영향은 domain/API 계약을 따른다.
- 최근 저축 내역은 Goal Account로 유입된 유효 Transaction 근거를 보여 주며 별도 Goal 기여금 record를 만들지 않는다.
- 전체 계좌번호나 private 금융 식별정보는 표시하지 않는다.

## 허용 action

- `계좌 연결`
- `목표 수정`

`목표에 돈 추가` 또는 동등한 별도 금액 입력 action은 만들지 않는다. 저축 행위는 실제 Account 사이의 Transaction으로 기록한다.

## Milestone과 motion

- 25%, 50%, 75%, 100% milestone에서만 비교적 큰 celebration을 허용한다.
- 일반 금액 갱신에는 작은 progress 변화만 사용하고 반복 animation을 실행하지 않는다.
- motion은 [Motion과 상호작용](interaction-motion.md)과 `prefers-reduced-motion`을 따른다.

## 상태와 접근성

- Goal 없음, 연결 Account 없음, 지표 계산 자료 부족, 조회 실패를 서로 다른 상태로 제공한다.
- 일부 보조 지표가 실패해도 확인 가능한 현재/목표 금액까지 숨기지 않는다.
- 고양이와 집은 text label, 금액, 달성률을 대체하지 않는다.
- chart와 progress는 색상만으로 값을 전달하지 않고 screen reader와 keyboard 탐색에 동등한 정보를 제공한다.
