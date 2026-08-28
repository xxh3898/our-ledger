# Backend

Java 25 + Spring Boot 4.1.1 + Gradle 9.7.1 + PostgreSQL/Flyway 기반 API다.

## 구성

```text
backend/
├─ build.gradle.kts
├─ settings.gradle.kts
├─ gradlew
├─ gradle/wrapper/
└─ src/
   ├─ main/java/io/github/xxh3898/ourledger/
   ├─ main/resources/db/migration/
   └─ test/
```

- `application.yml`: 공통 Flyway/JPA/Actuator 계약
- `application-local.yml`: local PostgreSQL 연결
- `application-test.yml`: test log와 profile 분리
- `V1__foundation.sql`: 업무 table 없이 Flyway 연속성을 시작하는 Foundation migration
- `V2__users_households.sql`: User, Household, HouseholdMember와 identity/membership 제약
- `V3__accounts_categories_transactions.sql`: Account, Category Group/Category, Transaction과 Household composite FK
- `V4__transaction_account_entries.sql`: Transaction의 Account balance effect와 Entry role 제약
- `V5__credit_card_liability_constraint.sql`: CREDIT_CARD/LIABILITY type-nature 제약

JPA는 모든 환경에서 `ddl-auto=validate`를 사용한다. schema 생성·변경의 기준은 Flyway다.

## 인증과 current Household

- default/production: `Cf-Access-Jwt-Assertion`만 token 입력으로 사용하고 RS256, issuer, audience, expiry/not-before, email을 검증한다.
- local/test: `X-Our-Ledger-Local-Identity`가 별도 filter chain에만 존재한다.
- `production`과 `local`/`test` profile을 함께 활성화하면 startup이 실패한다.
- 두 경로 모두 normalized email을 ACTIVE `users`에 매핑하고 정확히 하나의 `household_members`를 요구한다.
- `/actuator/health`는 공개하고 `/api/**`는 인증 뒤 내부 Household principal을 요구하며 나머지 endpoint는 deny한다.
- SPA CSRF는 `XSRF-TOKEN` cookie와 `X-XSRF-TOKEN` header를 사용한다. state-changing 요청에서 token이 없거나 다르면 403이다.

default/production 실행에는 저장소 밖의 `CLOUDFLARE_ACCESS_ISSUER`, `CLOUDFLARE_ACCESS_JWK_SET_URI`, `CLOUDFLARE_ACCESS_AUDIENCE`가 모두 필요하다. 실제 값은 sample, log, Git에 넣지 않는다.

## Transfer/Card Ledger

- Account/Category Group/Category는 current Household 조건으로 생성·조회·수정·archive한다.
- Transaction은 INCOME/EXPENSE/TRANSFER NORMAL을 허용하고 PRIMARY 또는 SOURCE/DESTINATION expected Entry set을 원자적으로 저장한다.
- CREDIT_CARD/LIABILITY 지출은 부채를 늘리고 ASSET→LIABILITY 이체는 자산과 카드 부채를 함께 줄인다.
- current balance는 opening balance와 논리삭제되지 않은 Transaction Entry의 delta 합이다.
- Transaction PATCH/DELETE는 optimistic `version`을 요구하고 stale request를 `409`로 거부한다.
- 모든 Member/Account/Category/Transaction/Entry 참조는 service의 current Household query와 PostgreSQL composite FK로 이중 검증한다.
- LIABILITY source TRANSFER와 REFUND는 Slice 3의 범위 밖이다.

## Bootstrap

`our-ledger.bootstrap.enabled`는 기본 `false`다. 명시적으로 활성화하면 `ApplicationRunner`가 외부 설정의 두 User와 한 Household를 한 transaction으로 provision한다. 정확한 기존 상태는 no-op이고, partial data나 다른 표시명·상태·role·Household는 fail-fast한다.

local sample은 `OUR_LEDGER_BOOTSTRAP_*`에 `example.test` identity만 제공한다. 최초 provision 뒤 enabled를 다시 `false`로 두며 production DB 실행은 별도 운영 gate다.

## 실행

repository root의 `.env.example`을 `.env.dev.local`로 복사해 local password를 설정한 뒤 개발 Compose를 사용한다.

```bash
docker compose --env-file .env.dev.local -f compose.dev.yaml --profile app up api
```

Java 25가 이미 있는 환경에서는 PostgreSQL만 Compose로 실행하고 Wrapper를 직접 사용할 수 있다.

```bash
cd backend
SPRING_PROFILES_ACTIVE=local ./gradlew bootRun
```

## 테스트

```bash
./scripts/verify-backend.sh
```

기본 test mode는 PostgreSQL 18.6 Testcontainers와 `@ServiceConnection`을 사용한다. host runtime이 없는 local fallback만 격리된 external test database를 사용하며, Docker socket을 build container에 mount하지 않는다.

`HealthEndpointDocsTest`는 clean database에 Flyway V1→V5가 적용되고 JPA가 schema를 validate하며 `/actuator/health`가 `UP`을 반환하는지 검증한다. 추가 통합 테스트는 DB 제약과 bootstrap, local current Household/CSRF, 가짜 RSA/JWK로 서명한 production JWT, Ledger delta·잔액·version·IDOR를 검증한다. Auth/Household와 Account/Category/Transaction HTTP test는 Spring REST Docs snippet을 생성한다.
