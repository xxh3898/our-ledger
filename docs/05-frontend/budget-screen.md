---
status: active
version: 0.3
last_updated: 2026-09-02
related:
  - 02-domain/budget.md
---

# 예산 화면

## 목적

이번 달에 얼마나 썼고 남은 예산이 얼마인지 빠르게 확인한다.

## 기본 카드

- 가계 전체 한도 (`HOUSEHOLD`)
- current Household의 각 실제 Member PERSONAL
- 공동

가계 전체 한도는 개인 Budget 합계가 아니라 개인·공동 지출 전체에 적용하는 독립 월 한도임을 화면과 입력 Sheet에서 설명한다. HOUSEHOLD와 PERSONAL/SHARED 카드는 같은 거래를 상위·세부 관점으로 보여 주며 카드 사용액을 서로 더하지 않는다.

각 카드에는 예산, 순소비, 남은 금액, 사용률을 표시한다.

- Budget row가 없어도 Transaction에서 계산한 사용액을 표시한다.
- 미설정은 `예산 미설정`, 0원 row는 `예산 0원`으로 구분한다.
- 0원에서 지출하면 `0원 예산을 초과했어요`를 text로 표시한다.
- 초과 시 음수 남은 금액과 초과 금액을 text로 표시한다.
- 사용률은 budgetAmount가 null 또는 0이면 만들지 않고 `spentAmount / budgetAmount`를 표시용 정수 percent로 반올림한다. 100%를 넘는 실제 비율을 허용한다.

## Category 예산

사용자가 설정한 세부 예산만 목록에 표시한다. 전체 Category에 강제 예산을 만들지 않는다.

- 신규 picker에는 active EXPENSE Category만 표시한다.
- Scope와 실제 Member 이름을 함께 표시한다.
- archived Category의 기존 Budget은 `보관됨` text와 함께 유지한다.

## 상호작용

- 월 이동
- 예산 생성·수정·삭제
- 사용액 클릭 시 거래 목록 drill-down

월은 `screen=budget&month=YYYY-MM` query에 저장해 새로고침과 browser back/forward를 보존한다. Router dependency는 추가하지 않는다.

생성·수정 Sheet는 월, 가계 전체 한도/실제 Member/공동, 전체 또는 EXPENSE Category, 0 이상 금액을 받는다. 가계 전체 한도를 선택하면 개인 Budget 합계가 아닌 별도 한도라는 도움말을 표시한다. 저장 중 중복 submit을 막고 server 오류 시 Sheet와 입력을 유지한다. `BUDGET_DUPLICATE`, `BUDGET_VERSION_CONFLICT`는 사용자가 이해할 수 있는 문구로 표시한다.

삭제는 exact 월·Scope·Category를 다시 보여 주는 2단계 확인을 거친다. Budget row만 삭제하고 Transaction과 사용액은 유지한다.

사용 내역은 기존 Transaction 목록을 month `from/to`, `type=EXPENSE`, scope/owner/category로 호출한다. NORMAL EXPENSE와 REFUND를 부호와 text로 구분하고 INCOME/TRANSFER를 섞지 않는다.

Budget 화면의 중앙 Paw FAB는 보이지 않는 Calendar 선택일을 재사용하지 않고 Household timezone 오늘 날짜로 Quick Entry를 연다.

## 표시 규칙

- 환불은 사용액을 감소
- 사용률 100% 초과 허용
- 예산 0원은 별도 표시하고 0으로 나누지 않음
- 색상만으로 위험 상태를 표현하지 않음
- page 본문은 자연스러운 세로 scroll을 사용하고 Bottom Navigation/Paw FAB safe-area 여백을 유지

## V1 제외

예산 초과 거래 차단, 자동 이월, 전월 자동 복사, 일별 강제 한도, AI 예산 추천은 제공하지 않는다.
