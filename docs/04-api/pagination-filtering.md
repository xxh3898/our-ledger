---
status: active
version: 0.2
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

Frontend의 `전체 / 치호 / 여자친구 / 공동`은 API에서 다음으로 변환한다.

- 전체: scope/owner 없음
- 치호: `scope=PERSONAL&ownerMemberId=<치호>`
- 여자친구: `scope=PERSONAL&ownerMemberId=<상대>`
- 공동: `scope=SHARED`

로그인 사용자 기준 `ME/PARTNER`를 DB에 저장하지 않는다.

## 월 달력

달력은 거래 전체 페이지를 반복 요청하지 않고 월 aggregate endpoint와 선택일 거래 endpoint를 분리할 수 있다. 월 범위는 Household timezone으로 계산한다.

## URL 상태

필터는 URL query에 반영해 새로고침, 뒤로가기, drill-down에서 유지한다. 잘못된 조합은 기본값으로 조용히 바꾸기보다 오류 또는 명시적 정규화를 사용한다.
