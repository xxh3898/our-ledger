---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - 05-frontend/quick-entry.md
  - 02-domain/goal.md
  - ADR-008
---

# 주요 사용자 흐름

## 최초 설정

V1 production에서는 실제 사용 전에 두 내부 User와 Household membership을 별도 bootstrap/provision 절차로 준비한다. 애플리케이션은 공개 회원가입이나 사용자 초대 기능을 제공하지 않는다.

1. Cloudflare Access에서 허용된 사용자가 OTP 또는 연결된 IdP로 인증한다.
2. 애플리케이션이 Access JWT를 검증하고 email claim을 내부 활성 User에 매핑한다.
3. User의 활성 Household membership을 확인한다.
4. Household 이름, 통화 `KRW`, 시간대 `Asia/Seoul`을 확인한다.
5. 개인·공동 Account와 opening balance를 등록한다.
6. 기본 Category를 확인하고 필요한 그룹·카테고리를 추가한다.
7. 결혼자금 Account와 Goal은 해당 Slice 이후 연결한다.

## 빠른 지출 입력

1. 중앙 `+` 버튼을 누른다.
2. `지출`을 선택한다.
3. 금액을 입력한다.
4. `치호 / 여자친구 / 공동` 중 소비 주체를 고른다.
5. Category와 결제 Account를 고른다.
6. 공동지출이면 Payer를 확인한다.
7. 저장한다.

일반 입력은 한 화면에서 끝나야 한다. 메모, 날짜·시간, 반복 설정은 고급 옵션으로 둔다.

## 카드대금 납부

1. 거래 유형 `이체`를 선택한다.
2. Source로 입출금 Account를 고른다.
3. Destination으로 신용카드 Account를 고른다.
4. 금액과 날짜를 입력한다.
5. 저장한다.

이 거래는 소비로 다시 집계되지 않는다.

## 환불

1. 원 지출 상세를 연다.
2. `환불 등록`을 누른다.
3. 환불 금액, 날짜, 환불 Account를 입력한다.
4. 누적 환불 가능액을 확인한다.
5. `REFUND` Transaction으로 저장한다.

단순 입력 오류는 환불이 아니라 원 거래 수정 또는 삭제로 처리한다.

## 반복거래

1. 월급, 구독, 적금 등 원형을 입력한다.
2. 주기, interval, 시작일, 종료일, 자동 반영 여부를 설정한다.
3. 스케줄러가 recurrence date별 실제 Transaction을 생성한다.
4. 사용자는 생성된 거래를 일반 거래처럼 조회한다.

## 결혼자금

1. 자산 화면에서 결혼자금 Goal을 생성한다.
2. 목표 금액과 목표일을 입력한다.
3. 하나 이상의 저축 Account를 연결한다.
4. 일반 Account에서 Goal Account로 이체한다.
5. 현재 보유금, 누적 마련금, 사용액, 예상 달성일을 확인한다.

Goal에 기여금을 별도로 입력하지 않는다.

## CSV 내보내기

1. 기간과 거래 필터를 선택한다.
2. 미리보기 건수와 컬럼을 확인한다.
3. CSV를 내려받는다.
4. 파일에는 Access JWT·cookie 등 인증정보, 전체 계좌번호, 내부 기술 식별정보가 포함되지 않는다.
