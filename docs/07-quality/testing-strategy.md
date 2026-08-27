---
status: active
version: 0.4
last_updated: 2026-08-27
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

Basic Ledger Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1→V4 clean 적용과 JPA `ddl-auto=validate`
- Account PERSONAL/SHARED CHECK, Member composite FK, KRW/last-four/savings 제약
- Category Group/type composite FK와 active case-insensitive name unique
- Transaction positive amount/scope/category CHECK, Member/Category/audit composite FK
- Entry의 Transaction/Account composite FK, nonzero delta, duplicate PRIMARY unique
- INCOME `+100000`, EXPENSE `-12000`, Transaction당 Entry 1개
- update 후 expected delta로 갱신되고 이전 delta가 누적되지 않음
- logical delete 후 목록/detail/잔액 제외, stale version `409`
- archived reference, unsupported posting, cross-household reference 거부와 atomic rollback

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

`App.test.tsx`는 Slice 2에서 identity loading/401/403을 보존하며 Account/Category 설정, 빠른 거래 생성, 서버 validation 실패 입력 보존, 최근 목록 edit/delete를 mock HTTP 경계에서 검증한다.

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

Basic Ledger는 `LedgerApiDocsTest`의 실제 current Household/CSRF request로 `ledger-account-*`, `ledger-category-*`, `ledger-transaction-*` create/list/detail/update/delete snippet을 생성한다.

## 회귀 우선순위

1. 재무 불변식
2. Household 경계
3. migration
4. 인증·인가
5. 핵심 입력·조회 흐름
6. 표현·디자인

## CI

`./scripts/verify.sh`가 단일 진입점이다. Pull Request required check에서 backend, frontend, docs, repository hygiene를 검증한다.
