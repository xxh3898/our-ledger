---
status: active
version: 1.0
last_updated: 2026-08-29
related:
  - ADR-008
  - 07-quality/financial-invariants.md
  - AGENTS.md
---

# 테스트 전략

## Foundation

- bootstrap class의 Spring Boot 구성 단위 테스트
- PostgreSQL 18.6 Testcontainers 기반 Spring context 기동
- clean database의 Flyway `V1__foundation.sql` 적용
- JPA `ddl-auto=validate` 계약
- `/actuator/health` HTTP `200`과 `UP` 응답
- React 기본 화면 component test
- ESLint, TypeScript typecheck, Vite production build

host에 Java/Node가 없는 local 환경은 Docker socket mount 없이 격리 external PostgreSQL과 build container를 사용한다. Hosted Backend CI는 기본 Testcontainers mode를 실행해 container 기반 연결 경로를 반드시 보완한다. 두 경로에서 같은 Flyway, JPA, health 관찰 결과를 검증한다.

## Backend

### 단위 테스트

- Transaction 생성 규칙
- Entry delta 계산
- 환불 가능액
- 저축액과 지표 공식
- 반복 날짜 계산
- Goal 예상일

### 통합 테스트

PostgreSQL Testcontainers를 사용한다.

- Flyway 전체 적용
- CHECK, unique, composite FK
- JPA mapping
- Household 격리
- 동시 수정 version 충돌
- 반복 생성 idempotency

Transfer/Card Ledger Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1→V5 clean 적용과 JPA `ddl-auto=validate`
- Account PERSONAL/SHARED CHECK, Member composite FK, KRW/last-four/savings, CREDIT_CARD/LIABILITY 제약
- Category Group/type composite FK와 active case-insensitive name unique
- Transaction positive amount/scope/category CHECK, Member/Category/audit composite FK
- Entry의 Transaction/Account composite FK, nonzero delta, duplicate PRIMARY unique
- INCOME `+100000`, ASSET EXPENSE `-12000`, 카드 EXPENSE `+amount`
- ASSET→ASSET SOURCE `-amount`/DESTINATION `+amount`, ASSET→LIABILITY 양쪽 `-amount`
- update 후 PRIMARY 또는 SOURCE/DESTINATION exact set으로 교체되고 stale role/delta가 남지 않음
- logical delete 후 목록/detail/잔액 제외, stale version `409`
- same/archived/unsupported/foreign transfer, invalid stored Entry set 거부와 atomic rollback
- Entry가 연결된 Account의 posting 분류 변경 거부와 기존 거래 조회·잔액 보존

Calendar Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- 현재월과 이전월 `NORMAL EXPENSE - REFUND EXPENSE` 합계와 차이
- INCOME/TRANSFER 순소비 제외, 논리삭제 거래 전체 제외
- ALL, 두 실제 Member의 PERSONAL, SHARED 분리
- PERSONAL owner 누락과 잘못된 scope/owner 조합 `400`
- 다른 Household Member를 PERSONAL owner로 요청할 때 `404`
- `Asia/Seoul` 자정 UTC 경계의 월·날짜 귀속
- 날짜별 순소비 합과 월 순소비의 같은 정의
- TRANSFER의 ALL 거래 수 포함과 PERSONAL/SHARED 제외

Budget Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1→V6 clean 적용과 JPA `ddl-auto=validate`
- `budget_month` 월 1일, amount 0 이상, scope-owner CHECK
- `UNIQUE NULLS NOT DISTINCT`의 null owner/category 포함 identity 중복 차단
- Member/Category composite FK와 service의 current Household 404
- active EXPENSE Category만 신규 연결하고 archived Category 기존 row는 표시
- HOUSEHOLD, 실제 Member별 PERSONAL, SHARED, Category 순소비 분리
- INCOME/TRANSFER/논리삭제 제외, REFUND 차감, Household timezone 월 경계
- 신용카드 구매 EXPENSE 포함과 카드대금 TRANSFER 제외
- Budget 미설정과 0원, 초과 후 Transaction 저장 허용
- duplicate pre-check와 DB unique race의 `BUDGET_DUPLICATE`
- stale PATCH/DELETE의 `BUDGET_VERSION_CONFLICT`
- Budget CRUD의 인증·CSRF·IDOR와 REST Docs canonical request/response

Pre-Statistics Refund Correctness Gate는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- ASSET EXPENSE Refund의 positive PRIMARY와 CREDIT_CARD/LIABILITY Refund의 negative PRIMARY
- 전체·여러 부분 환불의 active 합계와 original remaining
- original `PESSIMISTIC_WRITE` lock을 경합하는 동시 요청에서 한 요청만 성공해 누적 상한을 보존
- current Household, NORMAL EXPENSE, active row, valid PRIMARY exact set fail-closed
- archived Account/Category original의 실제 reversal 허용과 Scope/Owner/Payer/Category/Account 상속
- active Refund가 있는 original 금융 edit/delete 차단과 occurredAt/memo-only update 허용
- Refund generic PATCH 거부, version 기반 logical delete, delete 뒤 cap·Account·Calendar·Budget 복원
- dedicated Refund endpoint의 인증·CSRF·IDOR와 REST Docs canonical request/summary/error/delete

Statistics Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- NORMAL INCOME, NORMAL EXPENSE - REFUND EXPENSE와 논리삭제 제외
- 카드 구매 포함, 카드대금 TRANSFER 제외, PRIMARY Account breakdown 검산
- ALL/각 PERSONAL Member/SHARED Scope, foreign Member 404, invalid owner 조합 400
- Household timezone 포함 날짜와 custom partial month, 빈 calendar month 0 row
- current/comparison 독립 계산, previous 0 percent null, income 0 savings rate null
- subject 합과 Account 합이 summary 순소비와 정확히 일치
- Refund가 같은 Category/PRIMARY Account에서 차감되고 archived reference가 유지됨
- 비저축→저축, 저축→비저축, 저축→저축, 비저축→비저축 Transfer matrix
- savings Account EXPENSE가 저축 인출로 계산되지 않음
- PERSONAL/SHARED savings amount/rate unavailable
- savings activity impact 합과 ALL summary savings amount 일치
- 인증, validation, canonical Statistics/savings activity REST Docs

Recurring Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- Flyway V1→V7 clean 적용과 JPA `ddl-auto=validate`
- rule schedule CHECK, role별 Account template 제약, Household composite FK
- 생성 Transaction provenance의 둘 다 null 또는 둘 다 non-null CHECK와 논리삭제를 포함하는 full unique
- DAILY/WEEKLY/MONTHLY/YEARLY interval, 최초 anchor, 짧은 달과 윤년 clamp
- Household timezone local time의 due 경계와 지연 실행 catch-up batch 상한
- INCOME, ASSET EXPENSE, 카드 EXPENSE, TRANSFER의 canonical Entry·잔액·Calendar·Budget·Statistics 반영
- rule row lock을 경합하는 PostgreSQL worker의 발생일 중복 방지와 cursor 원자성
- 생성 Transaction 논리삭제 뒤 같은 발생일 재생성 차단
- template 수정의 향후 snapshot 적용과 기존 생성 거래 불변
- 일시정지·재개의 소급 미생성, 종료일, active/paused/ended 상태
- 한 규칙의 invalid template 실패가 다른 due 규칙을 막지 않는 격리
- active reference lifecycle 차단, stale version, validation, Household IDOR, 인증·CSRF
- canonical Recurring create/list/update/conflict REST Docs

Marriage Goal Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- Flyway V1→V8 clean 적용과 JPA `ddl-auto=validate`
- Goal name/type/positive target/version CHECK, Household MARRIAGE partial unique, future CUSTOM 비제한
- Goal/Account/Member audit composite FK와 Account 전체 assignment unique
- same Household 동시 MARRIAGE create 중 정확히 하나만 성공하고 stable `GOAL_ALREADY_EXISTS`
- eligible active savings ASSET 연결, archived/savings-disabled/LIABILITY 거부, foreign Account 404
- 동일 Account 동시 link 중 정확히 하나만 성공하고 stable `GOAL_ACCOUNT_ALREADY_ASSIGNED`
- Goal link가 Account lock을 가진 동안 동시 posting이 실제로 대기하고 `starting_balance`가 pre/post 중 하나의 완전한 값임
- current amount가 opening + active Entry delta 합이고 starting snapshot을 중복 가산하지 않음
- logical delete, Refund balance 효과, linked archived Account 유지, unlink 즉시 제외와 원장 불변
- Goal 경계 Transfer 네 방향, 다른 savings Account 유입, linked_at 이전, INCOME/EXPENSE/REFUND 비분류
- Household timezone 현재 월, 빈 달 포함 6개월 추세, 완료 3개월 정수 평균
- ACHIEVED/INSUFFICIENT_HISTORY/NON_POSITIVE_AVERAGE/PROJECTED와 ceil 예상 월
- impact 0 제외 최근 활동, 안정 정렬, recurring provenance
- 같은 version target 동시 PATCH 한 건만 성공, stale error, 인증·CSRF·Household 경계
- canonical Goal empty/read/create/update/link/unlink/error REST Docs

Auth/Household Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1/V2 clean 적용과 JPA schema validate
- email normalization과 case-insensitive duplicate 차단
- Household `KRW`/`Asia/Seoul` 기본값
- duplicate membership과 second OWNER DB 차단
- locked service transaction의 third Member 차단
- bootstrap exact rerun no-op과 partial/conflicting state fail-fast

### 인증·인가 테스트

production 인증 계약은 Cloudflare Access이므로 다음을 자동 검증한다.

- 유효한 Access JWT가 내부 활성 User에 매핑됨
- 잘못된 서명 거부
- 잘못된 issuer(`iss`) 거부
- 잘못된 audience(`aud`) 거부
- 만료 token 거부
- future `nbf` token과 missing email claim 거부
- 내부 User 미존재/비활성 상태 거부
- Household membership 없음 또는 ambiguous 상태 거부
- 다른 Household 리소스 접근 거부
- 일반 이메일 헤더만으로 인증할 수 없음
- production profile에서 개발용 identity adapter가 비활성
- state-changing 요청의 CSRF 또는 동등한 Origin 보호

Cloudflare 외부 서비스에 의존하지 않도록 테스트용 signing key/JWK와 test principal을 사용하되 production credential은 사용하지 않는다.

production 통합 테스트는 process-local HTTP JWK endpoint와 매 실행 생성한 RSA private key로 실제 RS256 token을 서명한다. repository에는 private key 파일이나 token fixture를 저장하지 않는다. production filter chain에 local identity filter가 없는지도 filter 목록과 HTTP 요청으로 확인한다.

### API 테스트

- 인증·인가·CSRF/Origin 보호
- validation과 error code
- filter 조합
- 삭제 후 계산 제외

`AuthHouseholdDocsTest`는 `/api/v1/me`, `/api/v1/households/current`, 401/403 error code, 임의 Household ID 비권한성, `XSRF-TOKEN`/`X-XSRF-TOKEN` 계약을 검증한다. test-only POST fixture는 token 없는 unsafe 요청을 403으로 거부하고 GET에서 받은 cookie token을 header로 보낸 요청만 허용한다.

## Frontend

- `/api/v1/me` loading과 정상 User/Household/role 렌더링
- 401 Cloudflare Access 인증 필요 상태
- 403 내부 User 미등록 상태
- 금액·날짜·필터 변환 단위 테스트
- 빠른 입력 form 컴포넌트 테스트
- 달력·예산·자산 상태 테스트
- 인증되지 않은 상태와 Access 재인증 이동 처리
- 핵심 사용자 흐름 E2E
- 모바일 viewport 접근성

`calendarState.test.ts`는 Household timezone 기본값, 잘못된 URL 정규화, 실제 Member ID, ALL/PERSONAL/SHARED API mapping, 월 이동 date clamp, Sunday-first grid를 검증한다.

`App.test.tsx`는 identity loading/401/403을 보존하며 다음 Calendar/Quick Entry 계약을 mock HTTP 경계에서 검증한다.

- Couple-first section 순서와 실제 Member 이름
- ALL/각 Member/SHARED의 월 요약·선택일 동일 적용
- transfer-only 무지출과 future Paw 제외
- 날짜 선택 URL/API, popstate 동기화
- 선택 날짜 전달과 current user PERSONAL 기본값
- numeric autofocus, ESC close, opener focus 복귀
- 중복 submit 방지, 500ms 성공 feedback, 같은 context 갱신
- 실패 시 Sheet·입력 보존
- 선택일 edit/delete 후 월·일 갱신
- 설정 Sheet의 Account/Category 기능 보존
- 미구현 하단 tab disabled

같은 test는 Refund Correctness Gate에서 다음 계약을 추가로 검증한다.

- NORMAL EXPENSE만 Refund action 제공하고 REFUND/INCOME/TRANSFER는 제외
- partial/full summary, amount/date/memo-only Sheet, Household timezone 오늘
- client/server cap error 입력 보존과 pending 중복 submit 방지
- 성공 뒤 Calendar aggregate·해당 날짜 목록 갱신
- REFUND text/sign, generic edit 제외, 원 지출 보존 삭제 확인
- Sheet autofocus, Escape/backdrop/close와 opener 또는 context fallback focus

같은 test는 Budget Slice에서 다음 계약을 추가로 검증한다.

- Budget destination active state와 Calendar 복귀, Statistics/Assets disabled
- HOUSEHOLD/실제 Member/SHARED 기본 카드와 Category Budget
- 미설정, 0원, 100% 초과의 text·금액 구분
- `screen=budget&month=YYYY-MM` 월 이동과 popstate
- 생성 성공 refresh, duplicate 실패 입력 보존, 수정 stale 오류, 2단계 삭제
- active EXPENSE Category picker와 archived Category 표시
- month/scope/owner/category `type=EXPENSE` drill-down과 REFUND 표시
- Budget Paw FAB의 Household timezone 오늘 날짜

같은 test와 `statisticsState.test.ts`는 Statistics Slice에서 다음 계약을 추가로 검증한다.

- Statistics destination 활성/`aria-current`, Assets disabled와 Calendar/Budget 이동 회귀
- 이번 달 ALL 기본값, 모든 preset의 이전 calendar range, custom same-day-count comparison
- invalid date/range/foreign Member canonicalization과 direct/back/forward URL state
- Member/SHARED API query mapping과 pending 중 stale 숫자 제거
- summary/comparison/month/Category/subject/Account의 amount와 계산 불가 text
- PERSONAL/SHARED 저축 unavailable 설명
- Transaction drill-down의 기간/Scope/type/Category/Account query와 REFUND `+금액`
- savings activity endpoint, Sheet focus/Escape/backdrop/opener 복귀
- Statistics Paw FAB의 Household timezone 오늘 날짜

같은 `App.test.tsx`는 Recurring Slice에서 다음 계약을 추가로 검증한다.

- 설정 Sheet의 active/paused/ended 목록과 schedule·Account·subject 표시
- 생성·수정 nested Sheet의 유형별 template, frequency/interval/date/time 입력
- pause/resume action과 소급 미생성 안내
- pending 중복 submit 방지, 실패 시 입력 보존, 성공 시 목록 refresh
- autofocus, Escape/backdrop close와 opener focus 복귀
- Calendar, Budget, Statistics, savings activity의 `반복` text badge

같은 `App.test.tsx`는 Marriage Goal Slice에서 다음 계약을 추가로 검증한다.

- Home의 Goal 없음 CTA 또는 actual current/target/rate/이번 달 card와 hardcoded shell 제거
- `?screen=goal` direct/refresh/back/forward와 새 Bottom tab 부재
- 상세 current/target/rate/remaining, projection 이유, 6개월 accessible SVG/table, linked Account/activity
- 생성 목표 금액 blank, 수정 version payload, pending 중복 submit 방지, stable error 뒤 입력 보존
- eligible Account 명시 선택, conflict 뒤 선택 보존, 연결/해제 확인과 read refresh
- archived linked Account와 `반복` provenance text, 수동 기여금 action 부재
- Sheet initial focus, Escape/backdrop/close, opener focus 복귀
- loading 중 이전 Goal 금융 수치 제거와 Goal 없음/연결 없음/error 분리

`budgetState.test.ts`는 timezone 현재 월, 잘못된 month 정규화, 연도 경계 월 이동과 Budget URL serialization을 검증한다.

## Production 보안 검증

배포 Gate에서는 자동 테스트 외에 다음을 확인한다.

- Access Allow 정책이 두 사용자 이메일만 허용
- `cloudflared` Access 검증 활성
- origin/API/DB 공용 포트 비노출
- Access를 우회하는 public hostname 부재
- 인증 token/cookie가 애플리케이션 로그에 남지 않음

실제 Cloudflare 설정 변경은 에이전트가 수행하지 않는다.

## 계약 테스트

Spring REST Docs를 사용해 API 구현과 문서를 동기화한다. `/actuator/health` 외에 Auth/Household Slice는 `current-user`, `current-household` response field snippet을 생성한다. 사람이 작성한 도메인 문서를 API 스키마로 대체하지 않는다.

Basic Ledger는 `LedgerApiDocsTest`의 실제 current Household/CSRF request로 `ledger-account-*`, `ledger-category-*`, `ledger-transaction-*` create/list/detail/update/delete, `ledger-refund-*`, `ledger-calendar-month` snippet을 생성한다. Budget은 `BudgetApiDocsTest`에서 `budget-create`, `budget-month`, `budget-update`, `budget-delete`, duplicate/version conflict snippet을 생성한다. Recurring은 `RecurringApiDocsTest`에서 `recurring-create`, `recurring-list`, `recurring-update`, `recurring-version-conflict` snippet을 생성한다. Marriage Goal은 `MarriageGoalApiDocsTest`에서 empty/read/create/update/link/unlink와 business error snippet을 생성한다. Statistics는 `StatisticsApiDocsTest`에서 `statistics-read-model`, `statistics-savings-activities`, `statistics-invalid-request` snippet을 생성한다.

## 회귀 우선순위

1. 재무 불변식
2. Household 경계
3. migration
4. 인증·인가
5. 핵심 입력·조회 흐름
6. 표현·디자인

## CI

`./scripts/verify.sh`가 단일 진입점이다. Pull Request required check에서 backend, frontend, docs, repository hygiene를 검증한다.
