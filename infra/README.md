# Infra

Slice 10C의 immutable production origin, backup/restore, operational status/monitor source, Slice 10D-1의 immutable Release/Deploy source harness, Slice 10D-2A candidate migration gate, Slice 10D-2B1 host state/shared operation lock, Slice 10D-2B2 restricted deployment transaction과 Slice 10D-3A1/A2 production Household/fresh-host bootstrap source를 관리한다. 현재 구현은 image build, non-root Nginx, normal `production` API, profile-gated `api-migration`/`api-bootstrap`, `web`/`api`/`postgres` Compose, host 운영 source, reusable Full CI, default-off release workflow, secret-free runtime-config artifact와 synthetic transaction/bootstrap harness까지다. 실제 GHCR publish, Tailscale/SSH, Mac mini ingress/host install/deploy/status/backup/migration/bootstrap/restore/monitor/HomeOps reporter, forced-command 설치, actual bootstrap input, Cloudflare Tunnel/Access 설정, production secret/User/DB, LaunchAgent, retention 삭제·외부복제와 alert activation은 포함하지 않는다.

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

repository root의 `compose.prod.yaml`은 이미 build/push된 exact API/Web image를 실행한다. normal `api`와 profile-gated `api-migration`/`api-bootstrap`은 같은 `${OUR_LEDGER_API_IMAGE}`를 사용하며 production Compose 자체는 host source를 build하거나 bind mount하지 않는다.

repository root의 `runtime-config.Dockerfile`은 Compose/Nginx와 공개 host script의 exact allowlist를 `scratch` artifact로 패키징한다. public backup wrapper와 artifact/internal core는 `scripts/backup-production.sh`, `scripts/backup_tools/`에 있고 fixed host state/lock/deployment/fresh-bootstrap worker와 test-only adapter는 `scripts/host_tools/`에 있다. restricted entrypoint는 `scripts/deploy-production.sh`, `scripts/bootstrap-production.sh`, status/monitor command는 `scripts/production-status.sh`, `scripts/monitor-production.sh`다. release contract와 runtime config detector는 `scripts/release_tools/`, `scripts/detect-runtime-config-change.sh`에 있다. host state, host/deploy/fresh-bootstrap transaction, restore, policy와 release 검증 진입점은 `scripts/verify-host-state.sh`, `scripts/verify-host-deploy-transaction.sh`, `scripts/verify-fresh-host-bootstrap.sh`, `scripts/verify-backup-restore.sh`, `scripts/verify-monitor-policy.sh`, `scripts/verify-release-transport.sh`다. production Compose에 deploy/bootstrap/backup/status/monitor service나 host backup/input bind mount를 추가하지 않는다.

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

## Release source 계약

`.github/workflows/deploy.yml`은 `main` exact HEAD에서 reusable Full CI를 먼저 실행한다. `OUR_LEDGER_DEPLOY_ENABLED` repository variable이 없거나 정확히 `true`가 아니면 publish와 deploy job은 건너뛰어 GHCR login/push, Tailscale과 SSH가 실행되지 않는다. workflow는 production concurrency `our-ledger-production`을 `cancel-in-progress: false`로 직렬화한다.

kill switch 이후 source contract는 API/Web/runtime-config를 같은 40자리 commit SHA tag, `linux/arm64`, OCI source/revision/version label로 publish하고 digest 형식을 확인한다. runtime-config detector는 last successful Production revision과 candidate 사이 exact source allowlist를 비교해 `keep` 또는 `update`만 반환하며 invalid/missing/non-ancestor range를 거부한다. restricted intent grammar는 다음 두 개뿐이다.

```text
deploy-our-ledger-v1 <sha> keep <actor>
deploy-our-ledger-v1 <sha> update <sha256:64hex> <actor>
```

GHCR token은 command argument가 아니라 SSH 표준 입력으로만 전달된다. B2 source의 `deploy-production.sh`는 이 exact intent와 stdin token을 fixed transaction에 연결하지만 Mac mini forced-command, actual credential과 runtime source는 설치하지 않았다. 따라서 kill switch를 활성화하거나 GHCR/Tailscale/SSH/production을 호출하지 않는다. fresh-bootstrap transaction source는 10D-3A2에 포함되지만 actual pre-current ingress/host install과 public route/secret/User/schedule 및 kill switch 활성화는 10D-3B의 별도 승인 대상이다.

local source 검증은 다음 command다.

```bash
./scripts/verify-release-transport.sh
```

이 gate는 helper/unit와 workflow source를 확인하고 amd64 host에서도 `scratch` runtime-config를 `--platform linux/arm64 --network none`으로 build/create/export해 exact regular-file allowlist와 `0600`/`0700` mode, expected directory hierarchy, label, forbidden material 부재, script help와 Compose render를 검증한다. BuildKit이 자동 생성한 parent directory mode는 고정하지 않으며 실제 host release directory owner/mode는 B1/A2 source가 강제하고 actual install은 10D-3B가 담당한다. 고유 development label의 image/container만 사용하고 cleanup 뒤 residue 0을 요구하며 registry login/push, Tailscale, SSH, production resource를 사용하지 않는다.

## Host state/shared operation lock source

production worker root는 `/Users/homeserver/Server/apps/our-ledger` 상수로 고정되고 CLI/environment path override가 없다. `runtime-config/releases/<digesthex>`, `state/deployment.json`, `pending/transaction.json`, relative `current`와 `operations/lock`만 B1 managed authority다. directory/lock은 current owner mode `0700`, JSON은 `0600`이며 runtime release file은 artifact allowlist의 `0600`/`0700`을 다시 검증한다.

`operations/lock`은 deploy와 standalone backup이 공유하는 atomic directory lock이다. holder가 있거나 stale/symlink/tampered lock이면 즉시 nonzero이고 자동 cleanup/stealing은 없다. public backup wrapper는 lock과 pending 검증 뒤 internal non-executable core를 호출한다. B2 deploy transaction은 이미 lock을 가진 상태에서 core를 직접 호출하므로 public skip flag 없이 self-deadlock을 피한다.

release directory는 exact digest에서만 정하고 같은 digest의 다른 content를 overwrite하지 않는다. pending은 새 transaction을 차단하고 crash 뒤 보존한다. current/state/pending은 relative confinement, formatVersion 2 exact schema, file fsync/atomic replace/directory fsync를 사용하며 candidate를 성공으로 추측하지 않는다. formatVersion 2는 B2 phase, actor/start 시각과 pre/post Flyway authority를 추가하며 production activation 전이므로 version 1 migration 없이 구버전을 fail closed한다.

```bash
./scripts/verify-host-state.sh
```

이 gate와 backup/restore의 test-only adapter는 owner-only temp root/disposable Compose만 사용한다. actual fixed root, GHCR/Tailscale/SSH/HomeOps와 production resource를 읽거나 쓰지 않으며 실제 host bootstrap/install은 10D-3B다.

## Restricted host deployment transaction source

future fixed entrypoint는 다음 source만 실행한다.

```text
deploy-our-ledger-v1 <sha> keep <actor>
deploy-our-ledger-v1 <sha> update <sha256:64hex> <actor>
```

`scripts/deploy-production.sh`와 `production_host deploy`에는 root, env, Compose, image, reporter, backup 또는 skip override가 없다. app root, project, env/backup/reporter path, image repository와 loopback target은 source에 고정된다. candidate image는 exact SHA tag, valid ID/repository digest, linux/arm64와 OCI source/revision/version을 모두 확인하며 runtime update는 exact digest export의 allowlist/mode를 다시 검증한다. owner-only temporary Docker config와 runtime tree는 fixed `/private/tmp` 아래 app root와 disjoint하게 만들고 cleanup한다.

shared `operations/lock` 아래 순서는 `current 검증 → artifact 검증/stage → API writer quiesce → verified backup core → pre-schema authority → same-image migration → post-schema authority → API/Web cutover → PostgreSQL/API/Web와 loopback readiness → env/current/state commit`이다. schema authority는 successful Flyway version, failed count 0과 deterministic history SHA-256이다. migration 뒤 schema가 바뀐 failure에는 previous image rollback, DB restore 또는 reverse migration을 자동 수행하지 않고 pending을 보존한다. 같은 authority에서만 previous exact image pair를 복구한다.

HomeOps reporter는 existing `report-homeops-event.py deployments`를 compact JSON stdin으로만 호출하고 `RUNNING/SUCCESS/FAILED/ROLLED_BACK` lifecycle을 사용한다. reporter endpoint/secret/HMAC/spool, stdout/stderr와 raw exception은 transaction이 읽거나 노출하지 않는다. direct network retry도 구현하지 않는다.

```bash
./scripts/verify-host-deploy-transaction.sh
```

이 gate는 32개 pure/synthetic test로 command/token, artifact identity, strict ordering, failure, formatVersion 2 crash/recovery, reporter/privacy와 cleanup을 검증한다. Docker/GHCR/Tailscale/SSH/HomeOps/public network와 `/Users/homeserver/Server`에 접근하지 않아 production mutation과 Docker residue는 0이다. source 준비는 forced-command/runtime install, credential, host dry run, backup/migration/deploy 또는 kill switch 활성화를 뜻하지 않는다.

## Fresh-host bootstrap transaction source

`scripts/bootstrap-production.sh`는 current가 없는 최초 activation만 위한 별도 ingress다. fixed production source는 app root `/Users/homeserver/Server/apps/our-ledger`, pre-current ingress `bootstrap-ingress`, env `.env`, one-time input `household-bootstrap.json`, backup `/Users/homeserver/Server/backups/our-ledger/data`, Compose project `our-ledger-production`, Docker `/usr/local/bin/docker`, loopback `127.0.0.1:18080`을 caller가 바꿀 수 없게 고정한다.

```text
bootstrap-our-ledger-v1 <sha> <sha256:64hex> <actor>
```

token은 stdin으로만 전달하며 root/env/input/Compose/image/reporter/skip/force/reset/delete option은 없다. ingress tree는 pulled runtime-config와 exact content/allowlist가 같아야 하고, current/state·foreign pending·unknown project resource·invalid owner-only input 또는 initial backup artifact가 있으면 fresh PostgreSQL을 만들기 전에 거부한다.

same shared lock 안에서 `artifact stage → PostgreSQL → migration → bootstrap → API/Web readiness → first backup → input unlink/fsync → current/state commit`을 수행한다. `FRESH_BOOTSTRAP` pending의 10개 phase는 normal deploy pending과 교차 소비되지 않고, crash 후 same request/candidate와 schema/Household/runtime/backup/input authority를 관찰해 forward resume한다. 자동 volume 삭제, domain repair, reverse migration/restore는 없다. 최종 state는 B2가 읽는 formatVersion 2이며 previous는 null이다.

```bash
./scripts/verify-fresh-host-bootstrap.sh
```

이 gate는 temp host와 synthetic input/credential, 고유 cleanup label의 disposable Compose만 사용해 migration 뒤 crash/re-entry, exact 2/1/2 bootstrap, readiness, custom backup, input 제거, final commit과 rerun 차단/data 불변을 검증한다. actual production root, GHCR login/publish, Tailscale/SSH/HomeOps/Cloudflare/public network를 사용하지 않으며 cleanup 뒤 resource residue 0을 요구한다. 실제 ingress/env/input 설치와 activation은 10D-3B다.

## 환경변수

`.env.production.example`은 변수 이름과 무해한 placeholder만 제공한다. fixed worker의 실제 production file authority는 app root의 owner-only `.env` 하나이며 Git 밖에서 관리한다. `.env.production` fallback이나 symlink alias는 지원하지 않는다.

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

필수 변수가 없거나 빈 문자열이면 Compose interpolation 또는 application startup이 fail-closed한다. normal `api`는 `OUR_LEDGER_BOOTSTRAP_ENABLED=false`, `OUR_LEDGER_RECURRING_SCHEDULER_ENABLED=true`, `SPRING_PROFILES_ACTIVE=production`과 Flyway disabled/JPA validate를 고정한다. `api-migration`은 `production,migration`, bootstrap/scheduler false, Flyway enabled/JPA validate/Web NONE을 고정한다. `api-bootstrap`은 `production,bootstrap`, bootstrap true, Flyway/scheduler false, JPA validate/Web NONE을 고정한다. 두 one-shot은 Cloudflare/local identity 값을 받지 않고 bootstrap의 Household/User 값은 environment allowlist에 존재하지 않는다.

## Render와 실행 명령

아래 명령은 fixed worker와 같은 `/Users/homeserver/Server/apps/our-ledger/.env` authority를 설명한다. production 실행은 별도 운영 승인, exact image SHA, 정상 backup, rollback 확인 뒤에만 수행한다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  config --quiet

docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  up --detach --wait
```

normal `up`은 schema를 변경하지 않는다. 10D-2B2 transaction은 B1 shared lock 아래 current writer quiesce와 verified backup 뒤 동일 exact candidate API image로 다음 one-shot을 먼저 실행하고, exit 0일 때만 위 normal `up`으로 cutover한다. 이 command shape는 source 계약이며 현재 production 실행 승인이 아니다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  run --rm --no-deps api-migration
```

one-shot은 host port와 장기 restart가 없고 application/database network에서 healthy existing PostgreSQL을 사용한다. Flyway/JPA 성공 뒤 `migration-validation: success`를 한 번 기록하고 exit 0, DB/history/schema/profile 설정이 잘못되면 nonzero다. 별도 migration image, host SQL checkout, mutable tag와 `migration` 단독 profile은 허용하지 않는다.

production Household bootstrap application-level shape는 다음과 같다. `api-bootstrap`은 database network만 사용하고 stdin의 최대 8 KiB exact JSON object를 처리해 `created|verified` marker 뒤 종료한다. 10D-3A2 fixed worker가 이 call을 source로 조합하지만 실제 production input/DB 실행은 10D-3B 승인 전에는 사용할 수 없다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  --profile bootstrap \
  run --rm -T --no-deps api-bootstrap < <owner-only-bootstrap-input>
```

`web`만 `127.0.0.1:${OUR_LEDGER_ORIGIN_PORT}`에 publish한다. API와 PostgreSQL은 host port가 없고 PostgreSQL은 internal database network에만 연결된다. `web`/`api`는 non-root, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, tmpfs, resource/pid limit와 graceful stop을 사용한다. PostgreSQL은 official entrypoint의 volume ownership 초기화를 보존하면서 host port·bind mount를 금지하고 project-scoped volume을 사용한다.

실제 env file을 사용한 `docker compose config` 전체 출력에는 resolved secret이 포함될 수 있으므로 저장·공유하지 않고 `config --quiet`을 기본으로 사용한다. 구조 검사는 합성 값만 사용하는 repository 검증 script가 JSON render를 처리한다.

## 검사

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  ps

docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  logs --tail=200 web api postgres
```

검사 시 secret/JWT/cookie를 출력하지 않는다. 외부 route가 연결되기 전에는 candidate migration exit, loopback origin, Nginx `/healthz`, 내부 API readiness, PostgreSQL health와 Flyway history를 확인한다. `/actuator/**`는 Nginx public origin에서 404이며 `/healthz`는 database나 API 상태를 노출하지 않는 Nginx 자체 응답이다.

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

## Monitor policy source harness

다음 command는 B1 status를 실행하고 repository 밖 minimal state를 atomic하게 갱신하며, 지원되는 filesystem `DISK_LOW` transition만 검증한 HomeOps reporter subprocess에 전달한다. source가 준비됐다는 사실은 actual production 실행, reporter/spool/API 호출, notification 또는 LaunchAgent 활성화 승인이 아니다.

```bash
./scripts/monitor-production.sh \
  --project-name our-ledger-production \
  --env-file /absolute/path/outside/repository/production.env \
  --backup-dir /absolute/dedicated/our-ledger-backups \
  --state-dir /absolute/dedicated/our-ledger-monitor-state \
  --homeops-reporter /absolute/installed/report-homeops-event.py
```

state directory는 current owner mode `0700`, reporter는 current owner의 group/other non-writable regular non-symlink executable이어야 하고 repository/state/backup과 canonical하게 disjoint해야 한다. reporter identity는 `report-homeops-event.py`로 고정한다. state formatVersion 2에는 failure streak/timestamp/status와 `DISK_LOW` episode sequence, active key, exact pending payload만 저장하며 HomeOps origin/secret/HMAC/spool, raw status, path, container/artifact identity와 사용자·금융 데이터를 저장하지 않는다. production activation 전이므로 이전 state migration은 없고 구버전/corrupt state는 fail closed한다.

worker는 persistent owner-only file의 non-blocking `flock`으로 동시 실행을 거부한다. disk 80% 진입/회복만 `DISK_LOW` ALERT/RECOVERED로 보내고 active episode 중 90% 진입은 중복 event를 만들지 않는다. pending은 reporter보다 먼저 durable save하고 exit 0 뒤 clear하며 실패·timeout·acceptance 뒤 state save failure는 다음 실행에서 같은 key로 먼저 재시도한다. service/origin/recurring/backup freshness와 filesystem unavailable은 local result에만 남는다. 실제 운영 bootstrap은 `launchd/com.homeserver.our-ledger-monitor.plist.example`의 fixed external path에 10D에서 별도 설치한다.

## Production one-shot backup

다음 command는 실제 production DB를 online logical read하고 지정한 host directory에 전체 재무 backup을 쓴다. source code가 준비됐다는 사실은 실행 승인이나 schedule 활성화를 의미하지 않는다. 실제 실행 전 exact project/env/directory, disk, 최신 정상 backup, 장애 대응 담당자와 restore Gate를 별도로 확인한다.

env file과 backup directory는 repository 밖 absolute regular path여야 하고 현재 관리 사용자 소유, group/other 권한 없음이 필요하다. directory는 미리 `0700`, env file은 `0600`으로 준비한다. `/`, repository/Workspace root, Docker/PostgreSQL data path, symlink와 `..` path는 사용할 수 없다.

```bash
./scripts/backup-production.sh \
  --project-name our-ledger-production \
  --env-file /absolute/path/outside/repository/production.env \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

command는 `docker compose config --quiet`만 사용하고 resolved config를 출력하지 않는다. 지정 project의 staged runtime-config artifact `compose.yaml`(source `compose.prod.yaml`)로 시작된 running/healthy PostgreSQL 18.6, project-scoped named volume/internal network를 확인한 뒤 container 내부 `POSTGRES_USER`/`POSTGRES_DB`와 기존 password 환경을 사용한다. API/Web을 restart하거나 PostgreSQL volume을 직접 읽지 않는다.

성공 artifact는 다음 구조다.

```text
our-ledger_production_<UTC>_v<schema>_<random>.backup/
├─ our-ledger_production_<UTC>_v<schema>_<random>.dump
├─ our-ledger_production_<UTC>_v<schema>_<random>.json
└─ our-ledger_production_<UTC>_v<schema>_<random>.sha256
last-success.json
```

bundle은 owner-only partial directory에서 nonzero, PostgreSQL custom magic, `pg_restore --list`, size와 SHA-256을 통과한 뒤 directory rename으로 공개된다. `last-success.json`은 verified bundle 뒤에만 atomic 교체된다. 실패는 nonzero exit이며 이전 valid bundle/marker를 덮어쓰지 않는다.

deploy와 standalone backup 동시 실행은 fixed app root의 shared `operations/lock`으로 차단한다. process crash로 stale lock이 남으면 자동 삭제하거나 steal하지 않는다. strict inventory는 삭제 없이 상태만 출력한다.

```bash
python3 scripts/backup_tools/backup_artifact.py inventory \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

retention dry-run plan은 latest verified 4개와 지난 7 KST day의 06:00 이후 첫 verified bundle을 keep으로 분류한다.

```bash
python3 scripts/backup_tools/backup_artifact.py retention-plan \
  --backup-dir /absolute/dedicated/our-ledger-backups
```

`pruneCandidates`를 포함해 어떤 artifact도 삭제하지 않는다. backup plist example은 `00:35/06:35/12:35/18:35` fixed external bootstrap과 `KeepAlive` 부재만 고정한다. 실제 prune, schedule, age/iCloud destination/암호화 복제와 production restore는 10D 승인 전까지 활성화하지 않는다.

## 중지와 rollback

일반 중지는 PostgreSQL volume을 보존한다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  down --remove-orphans
```

`--volumes`를 production 중지에 사용하지 않는다. image rollback은 app root `.env`의 API/Web image를 검증된 previous exact SHA로 바꾼 뒤 같은 `up --detach --wait` 명령을 실행한다. migration이 이전 image와 호환되는지 먼저 확인하며, production DB rollback이나 restore는 별도 runbook/승인 없이는 실행하지 않는다.

## Disposable smoke

```bash
./scripts/verify-production-runtime.sh
./scripts/verify-production-bootstrap.sh
./scripts/verify-fresh-host-bootstrap.sh
```

runtime smoke는 고유 Compose project, Docker가 할당한 loopback port, 합성 DB/Cloudflare 값, disposable volume을 사용한다. clean image build, config fail-closed, unmigrated normal API의 schema mutation 없는 failure, same-image V1→V8/JPA one-shot, idempotent rerun, Flyway/JPA/DB/profile failure, HTTP/bootstrap/scheduler 부재, static/SPA/cache, API 401, forged local identity 401, actuator 차단, hardening, normal restart와 graceful stop을 검사한다. bootstrap smoke는 별도 고유 labeled project와 합성 identity로 unmigrated→migration→created→verified→normal API lifecycle, strict input/profile/state/schema/DB failure, privacy와 V1~V8 불변을 검사한다. fresh-host smoke는 temp host와 별도 labeled project에서 migration crash/re-entry, first backup, input 소비와 final commit/rerun 차단을 검사한다. 각 `trap`은 성공·실패 시 해당 project의 container/network/volume과 검증 image tag만 제거하고 residue가 있으면 실패한다. 실제 production resource와 `/Users/homeserver/Server`는 참조하지 않는다.

Backup/Restore drill은 별도 entrypoint다.

```bash
./scripts/verify-backup-restore.sh
```

이 drill은 exact-HEAD API image, 합성 non-empty fixture, 고유 source/target/failure project와 각자 다른 disposable PostgreSQL volume을 사용한다. source에 candidate migration one-shot을 적용하고 실제 backup command로 dump를 만든 뒤 empty target에 fail-fast restore한다. restored V8에 같은 migration mode를 idempotent하게 재실행한 뒤 normal API의 Flyway-disabled JPA/readiness와 data/financial state/constraint 불변을 비교한다. dump는 owner-only temp directory에서만 사용하고 GitHub artifact로 업로드하지 않으며 성공·실패 후 exact resource residue 0을 요구한다.

production secret, tunnel credential, DB dump와 backup 파일은 Git에 커밋하지 않는다.

Operational status smoke는 별도 entrypoint다.

```bash
./scripts/verify-observability.sh
```

이 smoke는 exact-HEAD API/Web image와 고유 Compose project, 합성 credential/backup/financial fixture만 사용한다. recurring poll success와 isolated rule failure, API unavailable, process 재시작 후 not-yet-run reset, public actuator 404, status JSON privacy/read-only 경계와 container/network/volume/image/temp residue 0을 검증한다.

Monitor policy/HomeOps smoke는 별도 entrypoint다.

```bash
./scripts/verify-monitor-policy.sh
```

이 smoke는 pure evaluator, external state/backup/reporter contract, synthetic reporter subprocess, durable pending/episode, retention matrix와 plist parse/lint만 사용한다. actual production status/backup/HomeOps reporter·spool·API와 LaunchAgent를 사용하거나 host state를 설치하지 않는다.
