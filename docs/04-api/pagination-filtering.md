---
status: active
version: 0.5
last_updated: 2026-08-28
related:
  - 05-frontend/calendar-screen.md
---

# 페이지네이션과 필터

## 거래 목록

V1 데이터 규모와 구현 단순성을 고려해 offset pagination을 사용한다.

- `page`: 0부터 시작
- `size`: 기본 30, 최대 100
- 기본 정렬: `occurredAt desc, id desc`

동일 시각 거래에서도 ID로 안정 정렬한다.

## 필터

```text
from=2026-08-01
to=2026-08-31
type=EXPENSE
scope=PERSONAL
ownerMemberId=1
payerMemberId=2
categoryId=10
categoryGroupId=3
accountId=5
minAmount=10000
maxAmount=100000
query=점심
page=0
size=30
```

`accountId`는 Transaction의 PRIMARY, SOURCE, DESTINATION Entry 중 하나라도 해당 Account를 참조하면 일치한다. 따라서 이체는 출금·입금 Account 양쪽에서 조회된다.

## 전역 주체 필터

Frontend의 `전체 / 각 실제 Household Member 이름 / 공동`은 API에서 다음으로 변환한다.

- 전체: scope/owner 없음
- 각 Member: `scope=PERSONAL&ownerMemberId=<선택 Member ID>`
- 공동: `scope=SHARED`

로그인 사용자 기준 `ME/PARTNER`를 DB에 저장하지 않는다.

## 월 달력

달력은 거래 전체 페이지를 반복 요청하지 않는다. `GET /api/v1/calendar/month?month=YYYY-MM`에서 월 read model을 받고, 선택일은 기존 거래 목록에 같은 날짜와 scope/owner를 적용한다. 월과 선택일 경계는 Household timezone으로 계산한다.

- ALL: scope/owner query 없음
- Member: `scope=PERSONAL&ownerMemberId=<선택 Member ID>`
- SHARED: `scope=SHARED`

TRANSFER는 ALL의 날짜별 거래 수와 선택일 목록에는 포함하지만 소비에는 포함하지 않는다. Member/SHARED 조회에는 포함하지 않는다.

## Budget 사용 내역

Budget 화면의 사용액 drill-down은 새 원장 endpoint를 만들지 않고 거래 목록을 다음처럼 조합한다.

```text
from=<월 1일>&to=<월 말일>&type=EXPENSE
scope=PERSONAL&ownerMemberId=<Member ID>  # PERSONAL만
scope=SHARED                              # SHARED만
categoryId=<Category ID>                  # Category Budget만
```

HOUSEHOLD는 scope/owner를 보내지 않는다. `type=EXPENSE` 안에서 NORMAL 지출과 REFUND를 구분해 표시하며 INCOME/TRANSFER는 목록에 포함하지 않는다.

## Statistics와 drill-down

Statistics read model은 `from/to`와 optional `compareFrom/compareTo`를 받고 Calendar와 같은 Scope mapping을 적용한다. frontend는 raw Transaction 전체를 받아 합계를 다시 만들지 않는다.

주요 지표 drill-down은 같은 current `from/to`와 현재 Statistics Scope에 다음 filter를 더한다.

```text
수입       type=INCOME
순소비     type=EXPENSE
Category   type=EXPENSE&categoryId=<Category ID>
Account    type=EXPENSE&accountId=<PRIMARY Account ID>
Member     type=EXPENSE&scope=PERSONAL&ownerMemberId=<Member ID>
공동       type=EXPENSE&scope=SHARED
```

Category·Account row는 현재 Statistics Scope를 유지한다. 주체 row는 해당 row의 Scope로 좁힌다. 저축은 raw `type=TRANSFER`를 사용하지 않고 `/api/v1/statistics/savings-activities`를 조회한다.

## URL 상태

Calendar는 `month`, `view`, `date`, `memberId`를 URL query에 반영해 새로고침과 앞·뒤 이동에서 유지한다. Budget은 `screen=budget&month=YYYY-MM`을 사용한다. Statistics는 `screen=statistics`, `preset`, `view`, optional `memberId`, custom의 `from/to`를 사용하며 comparison range는 canonical preset/custom state에서 파생한다. frontend는 잘못된 월·날짜·기간을 Household timezone의 현재 상태로, foreign member를 ALL 보기로 명시적으로 정규화하고, 선택 날짜가 항상 표시 월에 속하도록 보장한다.
