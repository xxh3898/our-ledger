---
status: active
version: 0.2
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

### 인증·인가 테스트

production 인증 계약은 Cloudflare Access이므로 다음을 자동 검증한다.

- 유효한 Access JWT가 내부 활성 User에 매핑됨
- 잘못된 서명 거부
- 잘못된 issuer(`iss`) 거부
- 잘못된 audience(`aud`) 거부
- 만료 token 거부
- 내부 User 미존재/비활성 상태 거부
- 다른 Household 리소스 접근 거부
- 일반 이메일 헤더만으로 인증할 수 없음
- production profile에서 개발용 identity adapter가 비활성
- state-changing 요청의 CSRF 또는 동등한 Origin 보호

Cloudflare 외부 서비스에 의존하지 않도록 테스트용 signing key/JWK와 test principal을 사용하되 production credential은 사용하지 않는다.

### API 테스트

- 인증·인가·CSRF/Origin 보호
- validation과 error code
- filter 조합
- 삭제 후 계산 제외

## Frontend

- 금액·날짜·필터 변환 단위 테스트
- 빠른 입력 form 컴포넌트 테스트
- 달력·예산·자산 상태 테스트
- 인증되지 않은 상태와 Access 재인증 이동 처리
- 핵심 사용자 흐름 E2E
- 모바일 viewport 접근성

## Production 보안 검증

배포 Gate에서는 자동 테스트 외에 다음을 확인한다.

- Access Allow 정책이 두 사용자 이메일만 허용
- `cloudflared` Access 검증 활성
- origin/API/DB 공용 포트 비노출
- Access를 우회하는 public hostname 부재
- 인증 token/cookie가 애플리케이션 로그에 남지 않음

실제 Cloudflare 설정 변경은 에이전트가 수행하지 않는다.

## 계약 테스트

Spring REST Docs를 사용해 API 구현과 문서를 동기화한다. Foundation에서는 `/actuator/health` snippet만 생성하고 업무 API 문서는 해당 Slice의 request/response test와 함께 추가한다. 사람이 작성한 도메인 문서를 API 스키마로 대체하지 않는다.

## 회귀 우선순위

1. 재무 불변식
2. Household 경계
3. migration
4. 인증·인가
5. 핵심 입력·조회 흐름
6. 표현·디자인

## CI

`./scripts/verify.sh`가 단일 진입점이다. Pull Request required check에서 backend, frontend, docs, repository hygiene를 검증한다.
