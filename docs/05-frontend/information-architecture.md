---
status: active
version: 0.3
last_updated: 2026-08-27
related:
  - 01-product/benchmark-weple-money.md
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

이 상태 화면은 Slice 1에서 확정한 경계를 유지한다. success일 때만 Slice 2 Basic Ledger dashboard를 로드하고 401/403/error에서는 Ledger request를 시작하지 않는다.

## Slice 2 Basic Ledger

최종 Home/Calendar 정보구조 전에 다음 기능 panel만 제공한다.

1. current ASSET Account 잔액 요약
2. Account 생성·active 목록·archive
3. Category Group/Category 생성·active 목록·archive
4. INCOME/EXPENSE NORMAL 빠른 입력
5. 최근 거래 목록·수정·논리삭제

이 panel 구조는 기능 검증용이며 하단 탐색, Calendar/Home, 캐릭터·색상 asset 계약을 확정하지 않는다.

## 하단 탐색

```text
달력 | 예산 | + | 통계 | 자산
```

- `+`는 탭이 아니라 빠른 입력을 여는 주요 action이다.
- 설정은 상단 프로필 또는 더보기 메뉴에 둔다.
- 결혼자금은 달력 요약 카드와 자산 화면에서 접근한다.

## 달력 중심 Home

메인 화면은 월 요약, 달력, 선택일 거래 목록을 한 흐름에 제공한다. 별도의 복잡한 dashboard 탭을 만들지 않는다.

## 전역 필터

가능한 화면에서 동일한 의미로 사용한다.

```text
전체 | 치호 | 여자친구 | 공동
```

선택값은 달력·예산·통계의 조회 조건에 반영하되 화면별로 부적절한 경우 명확히 비활성화한다.

## 반응형

- 모바일을 기본으로 설계
- 데스크톱에서는 콘텐츠 폭을 제한하고 달력·상세 패널을 나란히 배치 가능
- 터치 target 최소 크기와 keyboard 탐색 지원

## Progressive Disclosure

일반 사용 흐름에는 핵심 정보만 보이고, 상세 필터·반복·고급 날짜·메모는 추가 조작으로 연다.
