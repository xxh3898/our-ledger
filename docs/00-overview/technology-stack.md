---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - README.md
  - 08-operations/deployment.md
---

# 기술 스택과 버전 정책

## 기준일

2026-08-27 기준 최신 안정판과 LTS를 우선한다. milestone, RC, beta, nightly는 운영 기준으로 사용하지 않는다.

## 확정 기술

| 영역 | 기준 |
|---|---|
| Java | Java 25 LTS. CI와 container image는 major 25로 고정하고 보안 patch는 정기 반영 |
| Spring | Spring Boot 4.1.1. 하위 Spring/Hibernate 버전은 Boot BOM 우선 |
| Build | Gradle 9.7.1 Wrapper, Kotlin DSL 권장 |
| Database | PostgreSQL 18.6 |
| Migration | Flyway. migration은 기능 Slice 순서로 추가 |
| ORM | Spring Data JPA. 복잡 집계는 명시적 query 사용 가능 |
| Frontend | React 19.2.8, TypeScript 6.0.3, Vite 8.2.2 |
| Node | Node.js 24.20.0 LTS (`.nvmrc`, Hosted CI) |
| 인증 | Spring Security + 서버 세션 |
| 배포 | Docker Compose + Nginx + Cloudflare Tunnel |

## 선택 원칙

- 가장 높은 버전보다 최신 안정판/LTS를 우선한다.
- runtime과 build tool은 wrapper, container digest 또는 lockfile로 재현 가능하게 고정한다.
- dependency version을 불필요하게 개별 override하지 않는다.
- 새 major 반영은 기능 PR에 섞지 않고 별도 Issue에서 검증한다.
- 보안 patch는 호환성 검증 후 가능한 한 빠르게 반영한다.

## 초기화 시 고정할 파일

- `backend/gradle/wrapper/gradle-wrapper.properties`
- `backend/build.gradle.kts`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/.nvmrc`
- backend/frontend container image

## Foundation 고정 결과

- Spring Boot와 하위 Spring/Hibernate/Flyway/Testcontainers version은 Boot 4.1.1 dependency management에 위임한다.
- Gradle Wrapper distribution은 9.7.1 URL과 공식 SHA-256으로 검증한다.
- npm direct dependency는 exact version, 전체 dependency tree는 `package-lock.json`으로 고정한다.
- 개발 Compose의 Java/Node image는 major toolchain 경계를 유지하며, Hosted CI는 Java 25와 Node.js 24.20.0을 검증한다.
- API 계약 도구는 runtime endpoint를 추가하지 않는 Spring REST Docs를 선택한다.

## 의도적으로 도입하지 않는 구성

V1 사용자 수와 트래픽에서는 Redis, Kafka, Kubernetes, 마이크로서비스가 필요하지 않다. 단일 Spring Boot API, 단일 PostgreSQL, 정적 frontend 배포로 운영 복잡도를 제한한다.
