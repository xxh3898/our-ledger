# Infra

Slice 10C-1의 immutable production origin, Slice 10C-2A의 backup/restore source gate와 Slice 10C-2B1의 operational status harness를 관리한다. 현재 구현은 image build, non-root Nginx, Spring `production` profile, `web`/`api`/`postgres` Compose, host one-shot custom backup, isolated restore drill과 privacy-safe read-only status snapshot까지다. 실제 Mac mini deploy/status/backup/restore, Cloudflare Tunnel/Access 설정, production secret/User/DB, schedule·retention·외부복제와 monitor/alert activation은 포함하지 않는다.

## 구조

```text
infra/
├─ docker/
│  ├─ api.Dockerfile
│  ├─ api.Dockerfile.dockerignore
│  ├─ HttpFetch.java
│  ├─ HttpHealthCheck.java
│  ├─ web.Dockerfile
│  └─ web.Dockerfile.dockerignore
└─ nginx/
   └─ nginx.conf
```

repository root의 `compose.prod.yaml`은 이미 build/push된 exact API/Web image를 실행한다. production Compose 자체는 host source를 build하거나 bind mount하지 않는다.

backup command와 artifact helper는 `scripts/backup-production.sh`, `scripts/backup_tools/`에 있고 status command는 `scripts/production-status.sh`, restore 검증 진입점은 `scripts/verify-backup-restore.sh`다. production Compose에 backup/status service나 host backup bind mount를 추가하지 않는다.

## Image 계약

| 단계 | 기준 image | runtime 포함 범위 |
|---|---|---|
| API build | Eclipse Temurin Java 25.0.4 JDK, digest 고정 | Gradle wrapper와 `src/main` build |
| API runtime | Distroless Temurin Java 25 Debian 13 nonroot, digest 고정 | `/app/app.jar`, compiled HTTP healthcheck/fetch helper |
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
| `OUR_LEDGER_RECURRING_INITIAL_DELAY_MS` | 아니오 | scheduler process 시작 뒤 첫 poll 지연, 기본 `0` |
| `OUR_LEDGER_RECURRING_POLL_DELAY_MS` | 아니오 | scheduler fixed delay, 기본 `60000` |

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

## Read-only production status

다음 command는 지정한 existing Compose project와 backup directory를 변경하지 않고 canonical JSON snapshot 하나를 stdout에 출력한다. 실제 production에서의 실행은 이 source 작업에 포함되지 않으며 exact project/env/backup target을 확인한 별도 운영 승인 대상이다.

```bash
./scripts/production-status.sh \
  --project-name our-ledger-production \
  --env-file /absolute/path/outside/repository/production.env \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

env file은 Git 밖 owner-only `0600`, backup directory는 Git 밖 owner-only `0700`이어야 한다. command는 exact `compose.prod.yaml`의 project/service/config label을 확인하고 `docker compose config --quiet`, `ps`, `docker inspect`, API container 내부의 GET-only `HttpFetch`만 사용한다. backup을 실행하거나 DB write, service restart/recreate, file 생성·삭제를 하지 않으며 resolved Compose config, container environment, raw internal body와 absolute path를 출력하지 않는다.

snapshot에는 service state/health/restart count, loopback `/healthz` status, 비식별 recurring scheduler raw signal, verified `last-success.json` freshness와 inventory count, backup filesystem capacity/available/used percent만 포함한다. missing/stopped/unhealthy/unreachable/invalid 상태를 success로 바꾸지 않는다. 정확한 JSON과 process-local 의미는 [`docs/08-operations/observability.md`](../docs/08-operations/observability.md)를 따른다.

## Production one-shot backup

다음 command는 실제 production DB를 online logical read하고 지정한 host directory에 전체 재무 backup을 쓴다. source code가 준비됐다는 사실은 실행 승인이나 schedule 활성화를 의미하지 않는다. 실제 실행 전 exact project/env/directory, disk, 최신 정상 backup, 장애 대응 담당자와 restore Gate를 별도로 확인한다.

env file과 backup directory는 repository 밖 absolute regular path여야 하고 현재 관리 사용자 소유, group/other 권한 없음이 필요하다. directory는 미리 `0700`, env file은 `0600`으로 준비한다. `/`, repository/Workspace root, Docker/PostgreSQL data path, symlink와 `..` path는 사용할 수 없다.

```bash
./scripts/backup-production.sh \
  --project-name our-ledger-production \
  --env-file /absolute/path/outside/repository/production.env \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

command는 `docker compose config --quiet`만 사용하고 resolved config를 출력하지 않는다. 지정 project의 exact `compose.prod.yaml`로 시작된 running/healthy PostgreSQL 18.6, project-scoped named volume/internal network를 확인한 뒤 container 내부 `POSTGRES_USER`/`POSTGRES_DB`와 기존 password 환경을 사용한다. API/Web을 restart하거나 PostgreSQL volume을 직접 읽지 않는다.

성공 artifact는 다음 구조다.

```text
our-ledger_production_<UTC>_v<schema>_<random>.backup/
├─ our-ledger_production_<UTC>_v<schema>_<random>.dump
├─ our-ledger_production_<UTC>_v<schema>_<random>.json
└─ our-ledger_production_<UTC>_v<schema>_<random>.sha256
last-success.json
```

bundle은 owner-only partial directory에서 nonzero, PostgreSQL custom magic, `pg_restore --list`, size와 SHA-256을 통과한 뒤 directory rename으로 공개된다. `last-success.json`은 verified bundle 뒤에만 atomic 교체된다. 실패는 nonzero exit이며 이전 valid bundle/marker를 덮어쓰지 않는다.

동일 directory의 동시 실행은 `.our-ledger-backup.lock`으로 차단한다. process crash로 stale lock이 남으면 다른 backup process가 없고 partial/final/marker 상태를 확인하기 전 자동 삭제하지 않는다. strict inventory는 삭제 없이 상태만 출력한다.

```bash
python3 scripts/backup_tools/backup_artifact.py inventory \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

보관 개수, 자동 prune, schedule, 외부 destination/암호화 복제와 production restore는 10D 승인 전까지 활성화하지 않는다.

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

Backup/Restore drill은 별도 entrypoint다.

```bash
./scripts/verify-backup-restore.sh
```

이 drill은 exact-HEAD API image, 합성 non-empty fixture, 고유 source/target/failure project와 각자 다른 disposable PostgreSQL volume을 사용한다. 실제 one-shot command로 dump를 만든 뒤 empty target에 fail-fast restore하고 Flyway/data/financial state/constraint/JPA/readiness를 비교한다. dump는 owner-only temp directory에서만 사용하고 GitHub artifact로 업로드하지 않으며 성공·실패 후 exact resource residue 0을 요구한다.

production secret, tunnel credential, DB dump와 backup 파일은 Git에 커밋하지 않는다.

Operational status smoke는 별도 entrypoint다.

```bash
./scripts/verify-observability.sh
```

이 smoke는 exact-HEAD API/Web image와 고유 Compose project, 합성 credential/backup/financial fixture만 사용한다. recurring poll success와 isolated rule failure, API unavailable, process 재시작 후 not-yet-run reset, public actuator 404, status JSON privacy/read-only 경계와 container/network/volume/image/temp residue 0을 검증한다.
