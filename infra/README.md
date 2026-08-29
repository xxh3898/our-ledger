# Infra

Slice 10C-1의 immutable production origin harness를 관리한다. 현재 구현은 image build, non-root Nginx, Spring `production` profile, `web`/`api`/`postgres` Compose와 disposable smoke까지다. 실제 Mac mini deploy, Cloudflare Tunnel/Access 설정, production secret/User/DB, backup/restore와 monitor activation은 포함하지 않는다.

## 구조

```text
infra/
├─ docker/
│  ├─ api.Dockerfile
│  ├─ api.Dockerfile.dockerignore
│  ├─ HttpHealthCheck.java
│  ├─ web.Dockerfile
│  └─ web.Dockerfile.dockerignore
└─ nginx/
   └─ nginx.conf
```

repository root의 `compose.prod.yaml`은 이미 build/push된 exact API/Web image를 실행한다. production Compose 자체는 host source를 build하거나 bind mount하지 않는다.

## Image 계약

| 단계 | 기준 image | runtime 포함 범위 |
|---|---|---|
| API build | Eclipse Temurin Java 25.0.4 JDK, digest 고정 | Gradle wrapper와 `src/main` build |
| API runtime | Distroless Temurin Java 25 Debian 13 nonroot, digest 고정 | `/app/app.jar`, compiled HTTP healthcheck |
| Web build | Node.js 24.20.0 Bookworm slim, digest 고정 | `npm ci`, Vite production build |
| Web runtime | Nginx unprivileged 1.30.4 Alpine, digest 고정 | `dist`, `/etc/nginx/nginx.conf` |
| Database | PostgreSQL 18.6 Alpine 3.23, digest 고정 | project-scoped named volume |

두 Dockerfile은 multi-stage이며 최종 API image에 shell/package manager/Gradle/source/test를, 최종 Web image에 Node/npm/node_modules/source를 남기지 않는다. base tag와 multi-platform manifest digest는 함께 고정한다. digest 갱신은 별도 검증 변경으로 처리한다.

local image build 예시는 다음과 같다. 이 명령은 image를 registry에 push하거나 production을 시작하지 않는다.

```bash
docker build --file infra/docker/api.Dockerfile --tag our-ledger-api:sha-replace-with-exact-commit .
docker build --file infra/docker/web.Dockerfile --tag our-ledger-web:sha-replace-with-exact-commit .
```

## 환경변수

`.env.production.example`은 변수 이름과 무해한 placeholder만 제공한다. 실제 값은 Git 밖의 exact production env file에서 관리한다.

| 변수 | secret | 목적 |
|---|---:|---|
| `OUR_LEDGER_WEB_IMAGE` | 아니오 | exact commit SHA tag 또는 digest의 Web image |
| `OUR_LEDGER_API_IMAGE` | 아니오 | exact commit SHA tag 또는 digest의 API image |
| `OUR_LEDGER_ORIGIN_PORT` | 아니오 | `127.0.0.1`에만 publish할 Nginx port |
| `POSTGRES_DB` | 아니오 | production database 이름 |
| `POSTGRES_USER` | 아니오 | production database role |
| `POSTGRES_PASSWORD` | 예 | production database password |
| `CLOUDFLARE_ACCESS_ISSUER` | 아니오 | Access JWT issuer URI |
| `CLOUDFLARE_ACCESS_JWK_SET_URI` | 아니오 | Access JWK set URI |
| `CLOUDFLARE_ACCESS_AUDIENCE` | 예 | Access Application audience |

필수 변수가 없거나 빈 문자열이면 Compose interpolation 또는 application startup이 fail-closed한다. `OUR_LEDGER_BOOTSTRAP_ENABLED=false`, `OUR_LEDGER_RECURRING_SCHEDULER_ENABLED=true`, `SPRING_PROFILES_ACTIVE=production`은 Compose에서 고정한다. local identity 환경변수는 production service에 전달하지 않는다.

## Render와 실행 명령

아래 명령의 `.env.production`은 저장소 밖 실제 운영 파일을 가리키는 예시다. production 실행은 별도 운영 승인, exact image SHA, 정상 backup, rollback 확인 뒤에만 수행한다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file .env.production \
  --file compose.prod.yaml \
  config --quiet

docker compose \
  --project-name our-ledger-production \
  --env-file .env.production \
  --file compose.prod.yaml \
  up --detach --wait
```

`web`만 `127.0.0.1:${OUR_LEDGER_ORIGIN_PORT}`에 publish한다. API와 PostgreSQL은 host port가 없고 PostgreSQL은 internal database network에만 연결된다. `web`/`api`는 non-root, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, tmpfs, resource/pid limit와 graceful stop을 사용한다. PostgreSQL은 official entrypoint의 volume ownership 초기화를 보존하면서 host port·bind mount를 금지하고 project-scoped volume을 사용한다.

실제 env file을 사용한 `docker compose config` 전체 출력에는 resolved secret이 포함될 수 있으므로 저장·공유하지 않고 `config --quiet`을 기본으로 사용한다. 구조 검사는 합성 값만 사용하는 repository 검증 script가 JSON render를 처리한다.

## 검사

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file .env.production \
  --file compose.prod.yaml \
  ps

docker compose \
  --project-name our-ledger-production \
  --env-file .env.production \
  --file compose.prod.yaml \
  logs --tail=200 web api postgres
```

검사 시 secret/JWT/cookie를 출력하지 않는다. 외부 route가 연결되기 전에는 loopback origin, Nginx `/healthz`, 내부 API readiness, PostgreSQL health, Flyway history를 확인한다. `/actuator/**`는 Nginx public origin에서 404이며 `/healthz`는 database나 API 상태를 노출하지 않는 Nginx 자체 응답이다.

## 중지와 rollback

일반 중지는 PostgreSQL volume을 보존한다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file .env.production \
  --file compose.prod.yaml \
  down --remove-orphans
```

`--volumes`를 production 중지에 사용하지 않는다. image rollback은 `.env.production`의 API/Web image를 검증된 previous exact SHA로 바꾼 뒤 같은 `up --detach --wait` 명령을 실행한다. migration이 이전 image와 호환되는지 먼저 확인하며, production DB rollback이나 restore는 별도 runbook/승인 없이는 실행하지 않는다.

## Disposable smoke

```bash
./scripts/verify-production-runtime.sh
```

smoke는 고유 Compose project, Docker가 할당한 loopback port, 합성 DB/Cloudflare 값, disposable volume을 사용한다. clean image build, config fail-closed, static/SPA/cache, API 401, forged local identity 401, actuator 차단, hardening, Flyway V1→V8, restart, graceful stop을 검사한다. `trap`은 성공·실패 시 해당 project의 container/network/volume과 검증 image tag만 제거하고 residue가 있으면 실패한다. 실제 production resource와 `/Users/homeserver/Server`는 참조하지 않는다.

production secret, tunnel credential, DB dump와 backup 파일은 Git에 커밋하지 않는다.
