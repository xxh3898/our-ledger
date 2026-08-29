---
status: active
version: 0.3
last_updated: 2026-08-29
related:
  - AGENTS.md
  - ADR-008
  - 08-operations/backup-restore.md
---

# 배포 구조

## 현재 구현 경계

Slice 10C-1은 아래 목표 구조 중 Mac mini origin의 immutable Web/API image, Nginx, Spring `production` profile, PostgreSQL Compose와 disposable smoke만 구현한다. 실제 image registry push, Mac mini production Compose 실행, Cloudflare Access/Tunnel, secret/User/DB, backup/restore와 monitor는 실행하지 않았다.

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

`compose.prod.yaml`의 현재 서비스:

- `web`: Node 24에서 build한 Vite `dist`를 제공하는 non-root Nginx 1.30.4
- `api`: shell/package manager/Gradle/source 없이 Distroless Temurin Java 25와 Spring Boot jar만 포함한 non-root runtime
- `postgres`: PostgreSQL 18.6 official image와 project-scoped named volume

`backup`과 `cloudflared` service는 10C-1 Compose에 포함하지 않는다. production DB는 internal database network에서만 접근하고 host port를 publish하지 않는다. API도 host port가 없으며 Nginx만 `127.0.0.1:${OUR_LEDGER_ORIGIN_PORT}`에 publish한다.

Web/API image의 build stage와 runtime stage는 분리하고 base image tag와 multi-platform manifest digest를 함께 고정한다. Web/API는 read-only root filesystem, non-root user, tmpfs, `cap_drop: ALL`, `no-new-privileges`, pid/resource limit를 적용한다. PostgreSQL은 official entrypoint의 초기 volume ownership 동작을 깨뜨리지 않는 범위에서 host publish/bind mount를 금지하고 resource/health/restart/graceful-stop을 적용한다.

## 환경 분리

- local
- test/CI
- production

production secret은 저장소에 두지 않는다. `.env.production.example`에는 변수 이름과 무해한 placeholder만 기록하고 실제 허용 이메일, Access audience, tunnel credential, DB password를 넣지 않는다. 환경변수 표와 render/start/inspect/stop 명령은 [`infra/README.md`](../../infra/README.md)를 따른다.

local/CI는 Cloudflare Access 없이 테스트 가능한 개발·테스트 전용 identity 경로를 사용할 수 있으나 production profile에서는 해당 우회 경로를 활성화하지 않는다.

## Nginx same-origin 계약

- `/`, `/index.html`, SPA deep link는 frontend `dist`에서 응답한다.
- `/api`와 `/api/**`는 `api:8080`으로만 proxy하고 SPA fallback에 들어가지 않는다.
- `Cf-Access-Jwt-Assertion`, original Host, `X-Forwarded-For`, `X-Forwarded-Proto`, request ID를 전달한다.
- upstream status/body/content type/`Content-Disposition`을 숨기지 않으며 API/CSV는 `no-store`다.
- `index.html`/SPA는 `no-store`, Vite hashed asset은 1년 immutable cache다.
- `/actuator/**`는 Nginx에서 404이고 `/healthz`는 `ok`만 반환하는 Nginx 자체 health다.
- server version token과 directory listing을 끄고 `nosniff`, frame deny, referrer 제한을 적용한다. 검증되지 않은 CSP는 추가하지 않는다.
- 현재 JSON request에 `client_max_body_size 2m`, API/CSV response에 `proxy_read_timeout 60s`를 사용한다. CSV response 크기는 request body limit 대상이 아니며 실제 사용량이 이 계약을 넘으면 별도 근거로 조정한다.

## Health

- API liveness/readiness
- PostgreSQL 연결 확인
- frontend 정적 파일 응답
- Compose healthcheck

readiness가 통과하기 전 신규 container로 traffic을 전환하지 않는다.

API container healthcheck는 JDK build stage에서 컴파일한 최소 `HttpClient` class로 내부 readiness를 검사한다. runtime image에 curl/package manager를 추가하지 않는다. Web healthcheck는 Nginx `/healthz`, PostgreSQL은 `pg_isready`를 사용한다.

Health endpoint를 인터넷에 별도 공개하여 Access를 우회하지 않는다. public Nginx는 actuator를 차단한다. 외부 모니터링이 필요하면 별도 service token 또는 최소 권한 Access 정책을 production gate에서 설계한다.

## 검증 하네스

`./scripts/verify-production-runtime.sh`는 고유 Compose project, ephemeral loopback port, 합성 DB/Cloudflare 값과 disposable volume으로 다음을 검증한다.

- missing/blank required env fail-closed와 rendered Compose security/network/mount 계약
- API/Web clean image build와 runtime content/non-root 검사
- Nginx static/SPA/cache/API 401/local identity 401/actuator 차단
- PostgreSQL Flyway V1→V8, JPA validate, API restart 뒤 persistence/readiness
- Spring graceful shutdown과 exact project container/network/volume/image tag residue 0

Hosted Full CI는 PR exact HEAD에서 같은 script를 실행한다. 이 smoke는 운영 Compose를 기동하거나 `/Users/homeserver/Server` resource를 참조하지 않는다.

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

10C-1 source/CI 통과는 위 production deploy Gate의 승인이 아니며 실제 public URL이나 service 상태를 변경하지 않는다.

## 롤백

애플리케이션 image rollback은 env file의 API/Web image를 검증된 previous exact SHA로 되돌린 뒤 같은 Compose `up --detach --wait`를 실행한다. 일반 `down`은 PostgreSQL volume을 보존하며 production에서 `down --volumes`를 사용하지 않는다.

애플리케이션 image 롤백과 DB rollback을 구분한다. forward-only migration으로 인해 이전 image가 새 schema와 호환되지 않으면 단순 image rollback을 금지한다.

인증 관련 롤백 시 Access 정책을 Bypass로 전환해 해결하지 않는다. 이전 안전한 애플리케이션 버전 또는 검증된 Access 설정으로 복구한다.
