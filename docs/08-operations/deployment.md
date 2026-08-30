---
status: active
version: 0.9
last_updated: 2026-08-30
related:
  - AGENTS.md
  - ADR-008
  - 08-operations/backup-restore.md
---

# 배포 구조

## 현재 구현 경계

Slice 10C-1은 아래 목표 구조 중 Mac mini origin의 immutable Web/API image, Nginx, Spring `production` profile, PostgreSQL Compose와 disposable smoke를 구현했다. Slice 10C-2A/B는 backup/restore, read-only status와 monitor policy source gate를 추가했다. Slice 10D-1은 `main` exact HEAD의 reusable Full CI, default-off Release workflow, linux/arm64 API/Web/runtime-config artifact와 restricted SSH intent의 source contract를 추가한다. Slice 10D-2A는 normal API의 schema mutation 권한을 제거하고 동일 candidate image의 명시적 one-shot migration/JPA validation lifecycle을 disposable PostgreSQL에서 고정한다. Slice 10D-2B1은 fixed host root, shared project operation lock과 digest-derived runtime-config release/current/pending/state primitive를 source와 temp-host gate로 고정한다. Slice 10D-2B2는 이 authority 위에 restricted wrapper, exact artifact 검증, backup/migration/cutover/readiness와 crash recovery를 조합한 source를 추가한다. Slice 10D-3A1은 같은 candidate API image의 production Household bootstrap stdin protocol과 deterministic no-HTTP lifecycle을 고정하고, Slice 10D-3A2는 current가 없는 host만 허용하는 별도 ingress와 durable forward recovery transaction을 source/disposable gate로 조합한다. Slice 10D-3B0은 deploy와 분리된 exact-SHA GHCR publish-only source를 추가한다. 실제 image registry push, Tailscale/SSH, Mac mini production Compose/state/status/backup/migration/bootstrap/monitor/HomeOps reporter, forced-command/pre-current ingress 설치, actual bootstrap input, Cloudflare Access/Tunnel, secret/User/DB, schedule·retention 삭제·외부복제와 production restore는 실행하거나 설치하지 않았다.

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
- `api-migration`: `migration` Compose profile에서만 보이는 동일 API image의 no-port, restart-disabled one-shot Flyway/JPA validation service
- `postgres`: PostgreSQL 18.6 official image와 project-scoped named volume

`backup`과 `cloudflared` service는 production Compose에 포함하지 않는다. backup은 관리 host가 existing `postgres` service 안의 logical client를 일회성 호출하며 source/DB volume 또는 Docker socket을 application container에 mount하지 않는다. production DB는 internal database network에서만 접근하고 host port를 publish하지 않는다. API도 host port가 없으며 Nginx만 `127.0.0.1:${OUR_LEDGER_ORIGIN_PORT}`에 publish한다.

Web/API image의 build stage와 runtime stage는 분리하고 base image tag와 multi-platform manifest digest를 함께 고정한다. Web/API는 read-only root filesystem, non-root user, tmpfs, `cap_drop: ALL`, `no-new-privileges`, pid/resource limit를 적용한다. PostgreSQL은 official entrypoint의 초기 volume ownership 동작을 깨뜨리지 않는 범위에서 host publish/bind mount를 금지하고 resource/health/restart/graceful-stop을 적용한다.

## 환경 분리

- local
- test/CI
- production

production secret은 저장소에 두지 않는다. `.env.production.example`에는 변수 이름과 무해한 placeholder만 기록하고 실제 허용 이메일, Access audience, tunnel credential, DB password를 넣지 않는다. 환경변수 표와 render/start/inspect/stop 명령은 [`infra/README.md`](../../infra/README.md)를 따른다.

local/CI는 Cloudflare Access 없이 테스트 가능한 개발·테스트 전용 identity 경로를 사용할 수 있으나 production profile에서는 해당 우회 경로를 활성화하지 않는다.

## Candidate migration과 normal startup

normal `api`는 `production` profile에서 Flyway를 비활성화하고 JPA `ddl-auto=validate`만 수행한다. 따라서 unmigrated 또는 candidate entity model과 맞지 않는 schema에는 startup을 실패시키되 table/history를 만들지 않는다. bootstrap은 false, recurring scheduler는 normal runtime 계약대로 true다.

`api-migration`은 같은 `${OUR_LEDGER_API_IMAGE}`를 `production,migration` profile로 실행한다. 이 mode만 Flyway를 활성화하고 JPA validate를 이어서 수행하며 Web application context, HTTP listener, bootstrap runner와 recurring scheduling을 만들지 않는다. 둘 다 성공하면 `migration-validation: success` 한 줄 뒤 Spring context를 닫고 exit 0, 어느 단계나 authority 검증이 실패하면 nonzero다. `migration` 단독, local/test 혼합, Flyway/JPA/Web/bootstrap/scheduler override와 datasource 누락은 fail closed한다.

10D-2B2 host worker가 B1 shared lock 아래 사용하는 canonical command shape는 healthy PostgreSQL과 exact candidate image가 확정된 기존 Compose에서 다음과 같다. 이 예시는 실제 production 실행 승인이 아니다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  run --rm --no-deps api-migration
```

one-shot이 0으로 끝난 뒤에만 normal `up --detach --wait` cutover를 진행한다. caller가 별도 migration image, host checkout SQL, mutable tag, arbitrary profile/command/path를 authority로 제공하지 않는다.

## Production Household bootstrap one-shot

normal `api`는 `OUR_LEDGER_BOOTSTRAP_ENABLED=false`를 강제하고 env override가 true면 startup을 거부한다. `api-bootstrap`만 동일 `${OUR_LEDGER_API_IMAGE}`를 `production,bootstrap` profile로 실행한다. Flyway와 recurring scheduler는 꺼지고 JPA `validate`가 먼저 완료되며 Web application context, HTTP listener, Cloudflare/local/test identity와 generic local bootstrap runner를 만들지 않는다.

입력은 CLI argument, Compose environment 또는 workflow input이 아니라 최대 8 KiB UTF-8 exact JSON object 하나를 stdin으로만 전달한다. owner/member email은 기존 normalizer를 사용하며 unknown/duplicate/missing/null/wrong-type/trailing data를 거부한다. 성공하면 `household-bootstrap: created` 또는 `household-bootstrap: verified` 한 줄 뒤 context를 닫아 exit 0으로 끝나고 failure는 raw JSON/PII/ID 없이 nonzero다.

10D-3A2 host transaction이 owner-only one-time input과 shared lock 아래 호출하는 application-level canonical shape는 다음과 같다. 현재 문서는 실제 production input 생성·전송 또는 DB 실행 승인이 아니다.

```bash
docker compose \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --file compose.prod.yaml \
  --profile bootstrap \
  run --rm -T --no-deps api-bootstrap < <owner-only-bootstrap-input>
```

empty migrated DB에서만 exact 2 User/1 Household/OWNER·MEMBER를 생성한다. 같은 input은 state/ID 변화 없이 verify하고 partial/mismatch/extra state를 자동 repair·delete·overwrite하지 않는다. migration과 bootstrap을 한 mode로 합치지 않으며 아래 10D-3A2가 `fresh DB → migration → bootstrap → normal readiness → first verified backup → durable commit`의 host ordering과 crash recovery를 별도로 제공한다.

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

API container healthcheck는 JDK build stage에서 컴파일한 최소 `HttpClient` class로 내부 readiness를 검사한다. 같은 build stage의 GET-only `HttpFetch`는 host status collector가 internal operations response의 HTTP status와 body를 읽을 때만 사용한다. runtime image에 curl/shell/package manager를 추가하지 않는다. Web healthcheck는 Nginx `/healthz`, PostgreSQL은 `pg_isready`를 사용한다.

`/actuator/health/operations`는 `recurringScheduler` raw signal만 details와 함께 제공하며 global `show-details: never`를 바꾸지 않는다. 이 component는 liveness/readiness group에 포함되지 않아 recurring failure가 API restart 신호가 되지 않는다. Health endpoint를 인터넷에 별도 공개하여 Access를 우회하지 않고 public Nginx는 `/actuator/**`를 계속 404 처리한다. 외부 모니터링이 필요하면 B1 host snapshot을 사용하고 service token 또는 최소 권한 Access 정책은 별도 production gate에서 설계한다.

## 검증 하네스

`./scripts/verify-production-runtime.sh`는 고유 Compose project, ephemeral loopback port, 합성 DB/Cloudflare 값과 disposable volume으로 다음을 검증한다.

- missing/blank required env fail-closed와 rendered Compose security/network/mount 계약
- API/Web clean image build와 runtime content/non-root 검사
- Nginx static/SPA/cache/API 401/local identity 401/actuator 차단
- unmigrated DB normal startup의 schema mutation 없는 failure
- same-candidate one-shot Flyway V1→V8/JPA validate와 idempotent rerun
- Flyway/JPA/DB/profile failure nonzero, HTTP/bootstrap/scheduler 부재와 V1~V8 byte 고정
- migrated normal API startup/restart 뒤 Flyway history와 persistence/readiness 유지
- Spring graceful shutdown과 exact project container/network/volume/image tag residue 0

Hosted Full CI는 PR exact HEAD에서 같은 script를 실행한다. 이 smoke는 운영 Compose를 기동하거나 `/Users/homeserver/Server` resource를 참조하지 않는다.

`./scripts/verify-production-bootstrap.sh`는 별도 고유 labeled Compose project와 합성 identity/credential만 사용해 unmigrated failure, V1→V8 migration, create/verified exact state, input/profile/state/schema/DB failure matrix, normal API no-replay, privacy와 resource residue 0을 검증한다. Hosted Full CI의 독립 `production-bootstrap` job도 actual production input/DB 없이 같은 gate를 실행한다.

`./scripts/verify-backup-restore.sh`는 별도 고유 source/target/failure Compose project, 합성 credential과 disposable volume으로 candidate one-shot→actual custom dump→integrity verification→restore를 실행한다. source와 restored target의 Flyway V1~V8, financial fixture, restored V8 migration rerun과 exact-HEAD normal production API readiness를 비교하고 모든 resource를 제거한다. 실제 production project/env/backup path는 사용하지 않는다.

`./scripts/production-status.sh`는 exact production Compose project, Git 밖 owner-only env file과 backup directory를 입력받아 service/origin/recurring/backup/filesystem raw JSON만 출력한다. `config --quiet`, `ps`, `inspect`와 internal GET 외에 container recreate/restart, DB/backup write, file cleanup을 하지 않는다. wrong project/config authority는 fail closed하고 개별 stopped/unreachable/invalid 상태는 나머지 관측과 함께 명시한다.

`./scripts/verify-observability.sh`는 같은 command를 exact-HEAD disposable stack에서 검증한다. synthetic recurring success/rule failure, API unavailable/restart reset, verified marker/inventory, public actuator 차단, privacy와 resource residue 0을 확인하며 실제 production resource를 사용하지 않는다.

`./scripts/verify-monitor-policy.sh`는 B1 snapshot 위의 threshold/streak, owner-only atomic state, non-blocking lock, HomeOps reporter subprocess와 durable `DISK_LOW` episode, monitor/backup plist를 pure/synthetic하게 검증한다. production status, 실제 HomeOps reporter/spool/API와 LaunchAgent를 사용하지 않는다.

## 10D-1 Release/Deploy source

`.github/workflows/deploy.yml`은 `main` push 또는 controlled manual dispatch에서 시작하지만 다음 경계를 갖는다.

- reusable `.github/workflows/full-ci.yml`을 먼저 호출해 같은 exact HEAD의 전체 gate를 통과시킨다.
- production concurrency는 `our-ledger-production`, `cancel-in-progress: false`다.
- repository variable `OUR_LEDGER_DEPLOY_ENABLED`가 정확히 `true`일 때만 publish/deploy job이 실행된다. variable이 없거나 다른 값이면 validation 이후 종료하며 GHCR login/publish, Tailscale과 SSH step은 실행되지 않는다.
- publish job만 `packages: write`, deployment history read 권한을 갖고 deploy job은 `packages: read`, Tailscale OIDC를 위한 `id-token: write`만 추가한다.
- publish/deploy privileged job의 third-party action은 mutable major tag가 아니라 검증된 exact commit SHA로 pin한다.
- API/Web/runtime-config는 `linux/arm64`, exact 40자리 `${{ github.sha }}` tag와 OCI source/revision/version label을 사용한다. `latest` 또는 caller 제공 image/tag를 사용하지 않는다.

`runtime-config.Dockerfile`은 `scratch`에서 시작하며 production Compose, Nginx 설정, backup/status/monitor와 검증 helper의 공개 source allowlist만 포함한다. `.env`, credential, private key, backup dump, marker, monitor state와 host-specific path는 포함하지 않는다. artifact contract는 각 regular file의 exact `0600`/`0700` mode와 예상 directory hierarchy, symlink·비정규 entry 부재를 고정하지만 BuildKit이 자동 생성한 parent directory mode를 security authority로 주장하지 않는다. B1/A2 source는 release/state/current와 fresh ingress의 owner/mode를 검증하고 실제 Mac mini app root와 bootstrap ingress 설치는 10D-3B에서 수행한다. `scripts/detect-runtime-config-change.sh`는 last successful Production revision부터 candidate까지 이 allowlist가 바뀌지 않았으면 `keep`, 변경·최초 bootstrap·명시적인 force면 `update`를 반환한다. revision이 없거나 candidate의 ancestor가 아니면 publish 전에 fail closed한다.

전송 payload는 다음 둘 중 하나다.

```text
deploy-our-ledger-v1 <exact-40-sha> keep <bounded-actor>
deploy-our-ledger-v1 <exact-40-sha> update <sha256:64-lowercase-hex> <bounded-actor>
```

helper는 이 grammar 외 extra argument, shell fragment, arbitrary path/image name과 invalid digest를 거부한다. workflow는 GHCR token을 command argument에 넣지 않고 restricted SSH process의 표준 입력으로만 전달한다. B2 `deploy-production.sh`도 `SSH_ORIGINAL_COMMAND`와 최대 8 KiB stdin token 외 caller override를 받지 않으며 token을 argument/environment/state/report에 넣지 않고 종료 시 mutable buffer를 비운다. source가 존재해도 forced-command와 credential이 설치되지 않았으므로 kill switch를 활성화할 운영 근거는 아직 없다.

## 10D-3B0 exact-SHA GHCR publish-only source

`.github/workflows/publish-release.yml`은 normal release/deploy workflow와 분리된 `workflow_dispatch` 전용 source다. `OUR_LEDGER_DEPLOY_ENABLED`를 읽거나 변경하지 않고 Tailscale, SSH, deployment permission, `Production` environment와 host command를 포함하지 않는다. production concurrency는 기존 writer와 같은 `our-ledger-production`, `cancel-in-progress: false`를 사용하며 publish job만 validation run 조회용 `actions: read`, source용 `contents: read`, artifact용 `packages: write`를 갖는다.

입력은 lowercase non-zero exact `release_sha`와 성공한 Release Source Harness `validation_run_id` 두 개뿐이다. login/build 전에 dispatch ref와 checked-out/remote live `main`, candidate의 live-main equality, run의 same repository, `main`, exact SHA, workflow name/path, completed/success를 fail closed로 결합한다. trusted live-main checkout은 helper authority로 남기고 candidate source는 별도 detached worktree에서 build한다.

API/Web/runtime-config는 candidate SHA의 `linux/arm64`, OCI source/revision/version identity로 tag 없이 digest-first push한다. package version metadata에서 세 candidate digest가 정확히 하나씩 확인된 뒤 exact SHA tag를 모두 preflight한다. absent는 candidate digest로 생성하고 same은 재사용하며 conflict, duplicate, malformed, unavailable은 final tag write 전에 실패한다. tag 생성 뒤 세 tag를 같은 digest로 다시 확인한다. metadata indexing은 bounded retry하고 실패를 success로 간주하지 않는다.

GHCR에는 source가 사용할 수 있는 documented conditional tag-create API가 없으므로 workflow 밖 registry admin의 동시 retag까지 원자적으로 막는다고 주장하지 않는다. repository-owned writer는 shared concurrency로 직렬화하고 exact SHA tag를 운영상 immutable로 취급한다. digest-first 이후 실패하면 untagged candidate digest나 일부 동일-candidate tag가 남을 수 있으며 기존 tag를 삭제·교체하지 않고 같은 exact request로 forward-complete한다.

`GITHUB_TOKEN`은 validation/package GitHub API와 GHCR login에만 사용하고 argv, artifact, summary나 raw error에 기록하지 않는다. local/PR/Hosted `verify-release-transport.sh`는 helper와 workflow source를 읽어 검증할 뿐 login/push를 실행하지 않는다. 이 source가 `dev`에 병합되고 별도 Release Gate로 `main`에 승격되기 전까지 Issue #59는 HOLD이며, source release만으로 actual package가 존재한다고 간주하지 않는다.

## 10D-2B1 host state와 shared operation lock

production worker의 app root는 source에서 `/Users/homeserver/Server/apps/our-ledger`로 고정한다. production CLI와 environment는 root, app/state/Compose path override를 받지 않는다. test-only `synthetic_host`만 dependency injection으로 mode `0700` temp root를 사용하며 actual fixed path를 읽거나 쓰지 않는다.

```text
/Users/homeserver/Server/apps/our-ledger/
├─ runtime-config/
│  ├─ releases/<64-lowercase-digest-hex>/
│  ├─ state/deployment.json
│  ├─ pending/transaction.json
│  └─ current -> releases/<digesthex>
└─ operations/lock
```

managed directory는 current user mode `0700`, state/pending JSON은 `0600`이다. shared operation lock은 `operations/lock` directory의 atomic `mkdir`로 non-blocking 획득한다. symlink·unexpected entry·다른 holder·crash 뒤 stale directory는 즉시 fail closed하며 PID만 보고 지우거나 steal하지 않는다. public `backup-production.sh`는 이 lock을 획득한 뒤 non-executable `backup_core.sh`를 호출하고 B2 deploy transaction은 이미 lock을 보유한 상태에서 같은 core를 직접 호출한다. `--skip-lock`이나 environment bypass는 없다.

runtime-config release 이름은 restricted intent의 exact `sha256:<64hex>`에서만 파생한다. artifact의 exact regular-file/directory allowlist와 `0600`/`0700`, current owner, hardlink/symlink/nonregular/unexpected entry 부재를 다시 검증한 뒤 owner-only partial tree의 file/directory fsync와 atomic directory rename으로 publish한다. 같은 digest·content는 재사용할 수 있지만 같은 digest의 다른 content는 overwrite하지 않는다.

`current`는 verified `releases/<digesthex>`를 향하는 relative symlink만 허용하고 temp symlink→atomic replace→runtime-config directory fsync 순서로 갱신한다. `deployment.json`과 `transaction.json`은 `formatVersion: 2` exact schema를 사용한다. pending은 비민감 actor/start 시각, candidate/previous identity, transaction phase와 pre/post schema authority만 저장하고 temp write→file fsync→atomic replace→directory fsync를 따른다. production activation 전 source이므로 formatVersion 1 migration/compatibility shim은 제공하지 않고 구버전을 fail closed한다. pending이 있으면 새 stage/transaction을 시작하지 않으며 candidate 성공을 추측하지 않는다.

이 B1 primitive의 install/bootstrap은 여전히 수행하지 않았다. API/Web cutover와 rollback을 조합하는 B2 source도 synthetic gate에서만 실행한다.

## 10D-2B2 restricted host deployment transaction

`scripts/deploy-production.sh`는 fixed current release의 `production_host deploy`만 실행한다. 실제 설치 시에도 production CLI는 root, env, backup, Compose, image repository, reporter, readiness target과 skip option을 받지 않는다. source에 고정된 authority는 다음과 같다.

- app root: `/Users/homeserver/Server/apps/our-ledger`
- Compose project: `our-ledger-production`
- env: app root의 owner-only `.env`
- backup: `/Users/homeserver/Server/backups/our-ledger/data`
- HomeOps reporter: HomeOps current release의 `report-homeops-event.py`
- image repository: `ghcr.io/xxh3898/our-ledger-{api,web,runtime-config}`
- local smoke: `127.0.0.1:18080`

future execution은 다음 순서를 건너뛰지 않는다.

```text
restricted command parse + stdin token
→ fixed host/source authority
→ project operation lock
→ current runtime identity check
→ linux/arm64 exact API/Web and runtime artifact 검증
→ runtime-config keep 또는 exact digest stage
→ current API writer quiesce
→ predeploy verified backup
→ pre-migration Flyway authority
→ 10D-2A same-candidate one-shot Flyway + JPA validate
→ post-migration Flyway authority
→ same-SHA API/Web cutover
→ PostgreSQL/API/Web + loopback readiness
→ exact image env + current/state durable commit
→ HomeOps deployment lifecycle
→ private Docker config/container/temp cleanup + token zeroization
```

- API/Web candidate는 requested 40자리 SHA tag, valid image ID/repository digest, linux/arm64와 OCI source/revision/version이 모두 일치해야 한다. runtime-config update는 command exact digest의 image를 owner-only `/private/tmp` 아래로 export하고 allowlist/mode/symlink·hardlink·size를 다시 검증한다. keep은 verified current identity를 그대로 재사용하며 fresh host는 두 mode 모두 거부한다.
- Compose subprocess는 fixed minimal environment와 external owner-only env만 사용해 ambient `DOCKER_HOST`, image 또는 secret override를 authority로 삼지 않는다. candidate cutover는 API/Web만 `--no-deps --pull never`로 바꾸고 PostgreSQL volume/network를 유지한다.
- pre/post schema authority는 latest successful Flyway version, failed migration 0과 deterministic history SHA-256이다. migration 이후 이 값이 바뀐 failure에는 previous image 호환성을 추측하지 않고 pending을 보존해 operator intervention으로 끝낸다. DB restore/reverse migration은 자동 실행하지 않는다.
- schema authority가 동일한 failure만 previous exact image pair 복구를 시도한다. readiness 전 current/state commit은 없고 external env는 두 image key만 file fsync→atomic replace→parent fsync로 바꾼다.
- pending phase는 `ARTIFACTS_VERIFIED`부터 `COMMITTING`까지 strict transition이다. recovery는 pending phase, observed container revision, schema와 readiness를 함께 확인하고 pre-migration abandoned, compatible rollback 또는 readiness-verified commit만 자동 처리한다. 모호한 post-migration 상태는 그대로 보존한다.
- HomeOps reporter는 `[canonical_reporter, "deployments"]`, `shell=False`, compact JSON stdin으로 actual vocabulary `RUNNING/SUCCESS/FAILED/ROLLED_BACK`만 받는다. event에는 branch `main`, candidate/previous SHA, bounded actor/stage/summary와 rollback 여부만 포함하며 endpoint/secret/HMAC/spool, path, token과 사용자·금융 data는 포함하지 않는다. reporter 장애는 application transaction 결과를 바꾸지 않는다.
- `down --volumes`, broad Docker prune, automatic DB rollback과 caller shell/Compose path/image를 금지한다. public Cloudflare smoke는 B2가 호출하지 않는다.

`./scripts/verify-host-deploy-transaction.sh`는 fake adapter/reporter와 owner-only temp state로 32개 command/token/artifact/order/failure/crash/recovery/privacy regression을 수행한다. 실제 Docker daemon, GHCR/Tailscale/SSH/HomeOps/public network와 `/Users/homeserver/Server`에는 접근하지 않는다. Hosted Full CI의 독립 `host-deploy-transaction` job도 같은 source gate만 실행한다.

## 10D-3A2 fresh-host bootstrap transaction source

`scripts/bootstrap-production.sh`는 normal B2의 verified-current-only ingress와 분리된 최초 activation 전용 source다. production 설치 경로는 `/Users/homeserver/Server/apps/our-ledger/bootstrap-ingress`, env는 app root의 `.env`, one-time input은 app root의 `household-bootstrap.json`, backup은 `/Users/homeserver/Server/backups/our-ledger/data`, Compose project는 `our-ledger-production`, loopback은 `127.0.0.1:18080`으로 고정한다. 이 경로와 파일을 실제 host에 설치하거나 생성하는 일은 10D-3B 전까지 수행하지 않는다.

restricted grammar는 다음 하나뿐이며 GHCR token은 stdin으로만 받는다.

```text
bootstrap-our-ledger-v1 <exact-40-sha> <sha256:64-lowercase-hex> <bounded-actor>
```

root, env/input/backup/Compose/image/reporter path, skip/force/repair/reset/delete option과 PII를 argument·environment에 받지 않는다. ingress 전체는 candidate runtime-config와 같은 exact allowlist/content여야 하며 owner regular file, no symlink/hardlink와 artifact mode를 다시 검증한다. env/input은 owner-only `0600`, input은 최대 8 KiB다. current/state가 있거나 normal deployment/foreign pending, unknown production project resource, non-empty initial backup authority가 있으면 DB mutation 전에 fail closed한다.

normal deployment와 같은 `operations/lock` 아래 다음 순서를 사용한다.

```text
exact API/Web/runtime-config artifact + ingress content 검증
→ immutable releases/<digesthex> stage
→ FRESH_BOOTSTRAP pending ARTIFACTS_VERIFIED
→ PostgreSQL only start
→ MIGRATION_STARTED → same-image V1→V8/JPA validate → schema authority
→ BOOTSTRAP_STARTED → same-image Household created/exact 2/1/2
→ normal API/Web + PostgreSQL/loopback/readiness/schema 재검증
→ first verified backup + marker SHA-256 authority
→ one-time input unlink + parent directory fsync
→ INPUT_CONSUMED → COMMITTING
→ relative current → existing formatVersion 2 deployment state(previous null) → pending 제거
```

fresh pending은 `transactionKind: FRESH_BOOTSTRAP` exact schema와 `ARTIFACTS_VERIFIED`, `POSTGRES_STARTED`, `MIGRATION_STARTED`, `MIGRATION_VERIFIED`, `BOOTSTRAP_STARTED`, `BOOTSTRAP_VERIFIED`, `READINESS_VERIFIED`, `BACKUP_VERIFIED`, `INPUT_CONSUMED`, `COMMITTING` phase를 사용한다. candidate/actor/start, post-schema와 backup marker hash만 저장하며 token, password, raw input, email/name/ID는 저장하지 않는다. normal B2 parser와 fresh parser는 서로의 pending exact schema를 거부한다. 최종 state는 기존 B2-compatible formatVersion 2를 그대로 사용한다.

DB mutation 뒤 실패에는 volume/User/Household/Flyway history를 삭제하거나 reverse migration/restore하지 않는다. 동일 request/candidate/pending만 observed schema, exact Household, runtime readiness, verified backup과 input 존재 여부를 재확인해 forward resume한다. 최초 uninterrupted bootstrap은 `created`만 허용하고 `BOOTSTRAP_STARTED`가 durable한 recovery에서는 같은 input의 exact `verified`도 허용한다. `INPUT_CONSUMED` 이후에는 input 없이 authority를 재검증해 commit할 수 있다. 성공 후 ingress 재실행은 current/state 때문에 항상 nonzero이며 이후 release는 normal B2만 사용한다.

`./scripts/verify-fresh-host-bootstrap.sh`는 pure phase/crash/cross-pending/privacy matrix와 고유 cleanup label의 disposable Docker project를 사용한다. local candidate API/Web/runtime artifact, fresh PostgreSQL, migration, migration 직후 crash/re-entry, bootstrap, normal readiness, verified backup, input 제거, B2-compatible commit과 rerun 차단/data 불변을 검증하고 container/network/volume/image residue 0을 요구한다. actual GHCR login, Tailscale, SSH, HomeOps, Cloudflare, public network와 `/Users/homeserver/Server`는 사용하지 않는다.

## 10D-3B activation boundary

B2, 3A1, 3A2와 3B0 완료는 deployment/application bootstrap/fresh transaction/publish-only source와 synthetic recovery·exact-state 검증이 끝났다는 의미다. 3B0 workflow의 실제 실행, owner-only actual env/input, pre-current ingress 설치, 실제 GHCR package/credential, Tailscale credential, authorized key forced command, Cloudflare/secret/User, actual production DB/migration/bootstrap/backup, schedule·replication, public smoke와 kill switch 활성화는 10D-3B 별도 승인 대상이다. one-shot migration/bootstrap architecture가 실제 schema나 2인 Household 의미와 맞지 않거나 기존 ADR/재무 계약을 바꿔야 하면 activation을 진행하지 않고 `DECISION_REQUIRED`로 중단한다.

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

10C source와 10D-1/10D-2A/10D-2B1/B2/10D-3A1/A2/3B0 source/CI 통과는 artifact publish workflow 실행, Tailscale/SSH, production deploy, ingress/host state 설치, actual bootstrap input/DB write, status/monitor 실행 또는 production backup/migration/restore/LaunchAgent Gate의 승인이 아니며 실제 public URL, service 또는 data 상태를 변경하지 않는다. `OUR_LEDGER_DEPLOY_ENABLED` 활성화도 별도 10D-3B 운영 결정이다.

## 롤백

애플리케이션 image rollback은 env file의 API/Web image를 검증된 previous exact SHA로 되돌린 뒤 같은 Compose `up --detach --wait`를 실행한다. 일반 `down`은 PostgreSQL volume을 보존하며 production에서 `down --volumes`를 사용하지 않는다.

애플리케이션 image 롤백과 DB rollback을 구분한다. forward-only migration으로 인해 이전 image가 새 schema와 호환되지 않으면 단순 image rollback을 금지한다.

인증 관련 롤백 시 Access 정책을 Bypass로 전환해 해결하지 않는다. 이전 안전한 애플리케이션 버전 또는 검증된 Access 설정으로 복구한다.
