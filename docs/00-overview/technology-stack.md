---
status: active
version: 0.1
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
| Frontend | React 19.2, TypeScript 6.0, Vite 8.x 안정 계열 |
| Node | Node.js 24 LTS 최신 patch |
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

## 의도적으로 도입하지 않는 구성

V1 사용자 수와 트래픽에서는 Redis, Kafka, Kubernetes, 마이크로서비스가 필요하지 않다. 단일 Spring Boot API, 단일 PostgreSQL, 정적 frontend 배포로 운영 복잡도를 제한한다.
