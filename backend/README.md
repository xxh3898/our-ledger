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

JPA는 모든 환경에서 `ddl-auto=validate`를 사용한다. schema 생성·변경의 기준은 Flyway다.

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

`HealthEndpointDocsTest`는 clean database에 Flyway V1이 적용되고 JPA가 schema를 validate하며 `/actuator/health`가 `UP`을 반환하는지 검증하고 Spring REST Docs snippet을 생성한다.
