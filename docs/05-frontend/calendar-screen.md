---
status: active
version: 0.4
last_updated: 2026-08-28
related:
  - 01-product/user-flows.md
  - 04-api/pagination-filtering.md
  - 05-frontend/design-system.md
  - 05-frontend/information-architecture.md
  - 05-frontend/marriage-goal.md
---

# Home/달력 화면

## 상태와 원칙

이 문서는 Slice 4에서 구현한 Couple-first Home/Calendar의 활성 디자인 계약이다. 월 read model, URL 상태, Scope, 선택일 목록, Quick Entry 진입, 설정 진입과 비활성 하단 tab까지 구현됐다. production 고양이 illustration과 Goal 실제 값은 각각 별도 asset 작업과 Slice 8 범위다.

- 한 viewport에 모든 내용을 압축하지 않고 하나의 자연스러운 세로 page scroll을 사용한다.
- 본문 안에 별도의 vertical scroll container를 만들지 않는다.
- 금융 숫자와 상태의 가독성을 캐릭터 장식보다 우선한다.
- [Concept Mockup v1](assets/concept-mockup-v1.png)은 색감·밀도·캐릭터 활용의 참고자료이며 pixel 단위 구현 계약이 아니다.

## 구성

1. 실제 Member 이름과 고양이 정체성을 사용하는 Couple header
2. 이번 달 소비 요약과 전월 비교
3. Marriage Goal hero card
4. `전체 / Member / 공동` Scope filter
5. 월 이동과 현재 월
6. 월 달력
7. 선택일 거래 목록
8. 고정 Bottom Navigation과 중앙 Paw FAB

```text
[고등어냥 치호] [삼색이 실제 Member]                 설정

우리 이번 달
1,284,500원 썼어요
지난달보다 82,000원 적어요

[ 우리 집까지                                  32.4% ]
[ 두 고양이 ━━━━━━━──────────── 집 ]
[ 이번 달 +1,800,000원                           ]

[전체] [치호] [실제 Member 이름] [공동]

< 2026년 8월 >
월간 달력

선택 날짜 거래 목록

달력       예산       [Paw FAB]       통계       자산
```

표시된 이름과 금액은 구조를 설명하는 예시이며 고정 product data가 아니다.

## Couple header와 월 요약

- 실제 Member 이름을 text로 표시하고 고양이는 보조 identity로 사용한다.
- 이번 달 핵심 금액은 `이번 달 소비`가 무엇인지 label과 함께 크게 표시한다.
- 전월 비교는 금액과 증가·감소 문구를 함께 제공한다. 색상이나 화살표만으로 의미를 전달하지 않는다.
- 알림·설정 같은 보조 action은 월 요약보다 시각 우선순위를 낮춘다.

## Marriage Goal hero

- Goal 이름, 현재/목표 또는 달성률, progress, 이번 달 저축을 한 카드에서 빠르게 파악하게 한다.
- 카드를 선택하면 [Marriage Goal 상세](marriage-goal.md)로 이동한다.
- Goal 값은 연결된 실제 Account와 Transaction에서 파생하며 Home에서 별도 기여금 입력을 제공하지 않는다.
- Goal이 없거나 연결 Account가 없을 때는 임의 금액을 만들지 않고 설정 가능한 empty state를 제공한다.

Slice 4에서는 Goal backend와 계산을 선행하지 않는다. 따라서 Home에는 실제 금액·달성률·action을 만들지 않는 shell/empty 안내만 두고, 위 실제 값과 상세 이동은 Slice 8에서 활성화한다.

## Scope filter

- `전체`, 각 실제 Member 이름, `공동`을 명시한다.
- 고양이 identity를 함께 사용할 수 있지만 text label을 대체하지 않는다.
- 선택 Scope는 월 요약, 달력, 선택일 거래 목록에 같은 의미로 적용한다.
- URL이나 동등한 navigation state에 월과 Scope를 보존해 새로고침·뒤로가기가 예측 가능해야 한다.

## 월 이동

- 이전/다음 월 button과 현재 월 label을 제공한다.
- swipe는 보조 기능이며 button을 대체하지 않는다.
- 긴 page를 scroll한 뒤에는 현재 월과 Scope를 보여 주는 compact sticky header로 축소할 수 있다. sticky 영역이 새 vertical scroll container가 되어서는 안 된다.

## 날짜 셀

- 일자
- 일별 순소비 또는 수입·소비 요약
- 오늘 표시
- 선택 상태
- 거래 존재 여부
- 선택 Scope 기준 무지출일의 작은 Paw marker

작은 화면에서 금액이 과도하게 겹치지 않도록 상세 수치는 선택일 목록에 둔다. 수입·지출·이체와 선택 상태는 색상만으로 구분하지 않는다.

## 선택일 거래 목록

- 날짜 선택 시 같은 page의 달력 아래에서 목록을 갱신한다.
- 거래명, 금액, 유형, Category, Account, 주체를 정보 우선순위에 따라 표시한다.
- NORMAL EXPENSE에만 `환불` action과 이미 환불/환불 가능 금액을 표시한다. 전액 환불이면 action 대신 `전액 환불됨`을 표시한다.
- REFUND row는 `Category 환불`, positive 금액, memo·Account와 원 지출 상쇄 설명을 text로 표시하고 generic 수정 action을 제공하지 않는다.
- REFUND 삭제 전에는 “환불 기록만 삭제되며 원 지출은 유지”됨을 확인한다.
- 삭제된 거래는 목록과 모든 aggregate에서 제외한다.
- 목록이 길어도 별도 고정 높이 scroll 영역을 만들지 않고 page 흐름에 이어 붙인다.

## 상호작용

- 월·Scope·날짜 변경은 영향을 받는 요약과 목록을 같은 query 조건으로 갱신한다.
- 요약 금액을 선택하면 같은 조건의 거래 목록을 확인할 수 있어야 한다.
- 중앙 Paw FAB는 [빠른 입력](quick-entry.md)을 연다.
- Refund는 Quick Entry 거래 유형 tab이 아니라 NORMAL EXPENSE row에서 Refund Sheet를 연다.
- Bottom Navigation은 `달력 / 예산 / Paw FAB / 통계 / 자산` 순서를 유지하며 FAB는 navigation tab이 아니다.
- fixed 영역이 기기 safe area나 본문의 마지막 거래를 가리지 않도록 하단 여백을 확보한다.

## 상태

- 초기 로딩에는 layout shift를 줄이는 skeleton을 사용한다.
- 월 거래 없음과 선택일 거래 없음을 구분한다.
- 월 aggregate 실패와 선택일 목록 실패를 분리해 정상 영역까지 숨기지 않는다.
- 삭제·수정 후 aggregate와 목록을 함께 무효화한다.
- Refund 생성·삭제 후 Calendar 월 aggregate와 선택일 목록을 함께 무효화한다.
- 이전 조건의 금액을 새 조건의 결과처럼 남겨 두지 않는다.

## Refund Sheet

- 원 거래 Category·금액·PRIMARY Account와 이미 환불/환불 가능 금액을 먼저 보여 준다.
- 편집 control은 환불 금액, Household timezone 오늘이 기본인 날짜, optional memo만 제공한다.
- 환불 금액은 remaining 이하이며 pending 동안 중복 submit과 close를 막는다.
- client/server 오류 뒤 Sheet와 입력을 유지하고 stable error code의 사용자 메시지를 표시한다.
- 성공 text를 짧게 표시한 뒤 닫고 원래 Calendar context를 갱신한다.
- backdrop, close button, Escape로 닫을 수 있으며 opener로 focus를 돌린다. 전액 환불로 opener가 사라지면 선택일 제목을 fallback focus로 사용한다.

## 접근성

달력은 시각적 grid뿐 아니라 날짜 button의 접근 가능한 이름, 현재 날짜, 선택 상태를 제공한다. 고양이·Paw·색상은 실제 Member 이름, 거래 유형, 무지출 상태, 환불 상태 text를 대체하지 않는다. keyboard focus 순서는 page의 시각 순서와 일치해야 한다.

## Slice 4 구현 상태

- Couple header는 API의 실제 Member 이름과 현재 사용자 `나` 표시, CSS avatar placeholder를 사용한다.
- 월 요약·날짜별 상태·선택일 목록은 같은 ALL/PERSONAL/SHARED 조건으로 각각 독립 로딩하며 이전 조건 값을 남기지 않는다.
- 무지출 Paw는 Household timezone 기준 미래가 아닌 날짜에서 순소비가 0일 때 표시한다. 수입/이체만 있는 날도 포함한다.
- `month/view/date/memberId` URL을 정규화하고 `popstate`와 동기화한다. 월 이동 시 선택 일자를 새 월 마지막 날까지 clamp한다.
- 중앙 Paw FAB는 선택 날짜를 Quick Entry에 전달하지만 Calendar scope를 입력 기본값으로 복사하지 않는다.
- NORMAL EXPENSE row는 Refund summary를 current Household 경계에서 읽고 partial/full 상태 및 Refund Sheet 진입을 제공한다.
- REFUND row는 별도 sign/text, no generic edit, 2단계 logical delete를 제공한다.
- 예산·통계·자산 tab은 `준비 중`과 disabled 상태로만 표시하며 가짜 화면으로 이동하지 않는다.
- 계좌·Category 관리는 상단 설정 Sheet에서 계속 접근할 수 있다.
