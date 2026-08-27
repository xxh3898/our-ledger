---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - AGENTS.md
  - ADR-008
  - 08-operations/backup-restore.md
---

# 배포 구조

## 목표 구조

```text
사용자 브라우저/PWA
→ Cloudflare Access
→ 허용 이메일 2명 인증
→ Cloudflare Tunnel
→ cloudflared Access JWT 검증
→ Mac mini Nginx
→ Spring Security Access JWT 검증 / 내부 User 매핑
→ frontend 정적 파일 / Spring Boot API
→ PostgreSQL
```

Cloudflare Access는 외부 인증 경계이고 Spring Security는 검증된 identity를 내부 User 및 Household 권한으로 연결한다.

관리 접근은 Tailscale을 사용한다. 공유기에서 애플리케이션, Nginx origin, API 또는 DB 포트를 공용 인터넷에 직접 개방하지 않는다.

## Cloudflare Access

production hostname에는 Cloudflare Access Self-hosted Application을 연결한다.

- Allow 정책은 실제 사용자 두 명의 이메일만 명시한다.
- 실제 이메일, Application audience, team name, tunnel credential은 저장소에 커밋하지 않는다.
- One-time PIN을 사용할 경우 이메일 allowlist와 함께 사용한다.
- Access 정책을 우회하는 public hostname 또는 별도 origin 공개 경로를 만들지 않는다.

## cloudflared Origin 보호

production ingress에서는 `cloudflared`의 Access JWT 검증을 요구한다.

개념 설정:

```yaml
originRequest:
  access:
    required: true
    teamName: ${CLOUDFLARE_ACCESS_TEAM_NAME}
    audTag:
      - ${CLOUDFLARE_ACCESS_AUD}
```

위 값은 설명용 변수명이며 실제 값은 secret/운영 설정으로 주입한다.

`cloudflared` 검증을 통과한 뒤에도 Spring Security에서 `Cf-Access-Jwt-Assertion`의 서명, issuer, audience, 만료를 검증한다.

## Container

예상 서비스:

- `web`: Nginx 또는 frontend serving
- `api`: Spring Boot Java 25
- `db`: PostgreSQL 18
- `backup`: pg_dump 실행 도구 또는 host scheduler
- `cloudflared`: 기존 운영 방식에 따라 별도 또는 공용 tunnel

production DB는 Docker internal network에서만 접근하도록 하고 host의 `5432`를 공용 인터페이스에 publish하지 않는다. API와 Nginx도 Cloudflare Tunnel 또는 명시된 로컬 경계 밖으로 직접 공개하지 않는다.

## 환경 분리

- local
- test/CI
- production

production secret은 저장소에 두지 않는다. `.env.example`에는 변수 이름과 목적만 기록하고 실제 허용 이메일, Access audience, tunnel credential, DB password를 넣지 않는다.

local/CI는 Cloudflare Access 없이 테스트 가능한 개발·테스트 전용 identity 경로를 사용할 수 있으나 production profile에서는 해당 우회 경로를 활성화하지 않는다.

## Health

- API liveness/readiness
- PostgreSQL 연결 확인
- frontend 정적 파일 응답
- Compose healthcheck

readiness가 통과하기 전 신규 container로 traffic을 전환하지 않는다.

Health endpoint를 인터넷에 별도 공개하여 Access를 우회하지 않는다. 외부 모니터링이 필요하면 별도 service token 또는 최소 권한 Access 정책을 production gate에서 설계한다.

## 배포 Gate

에이전트는 production deploy와 Cloudflare Access/Tunnel 설정 변경을 수행하지 않는다. 사용자가 다음을 확인한 뒤 명시적으로 실행한다.

- image/tag 또는 commit SHA
- migration 영향
- backup 최신성
- rollback 절차
- Cloudflare hostname 및 Access Application
- 허용 사용자 정책
- `cloudflared` Access 검증 설정
- health check

## 롤백

애플리케이션 image 롤백과 DB rollback을 구분한다. forward-only migration으로 인해 이전 image가 새 schema와 호환되지 않으면 단순 image 롤백을 금지한다.

인증 관련 롤백 시 Access 정책을 Bypass로 전환해 해결하지 않는다. 이전 안전한 애플리케이션 버전 또는 검증된 Access 설정으로 복구한다.
