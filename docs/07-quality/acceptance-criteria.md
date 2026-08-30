---
status: active
version: 1.2
last_updated: 2026-08-30
related:
  - 00-overview/roadmap.md
  - ADR-008
  - 08-operations/backup-restore.md
---

# V1 인수 기준

## 기능

- Cloudflare Access에서 허용된 두 사용자가 각자 인증되고 같은 Household 데이터를 본다.
- 검증된 Access identity가 내부 활성 User에 매핑되지 않으면 접근이 거부된다.
- 수입·지출·이체를 생성·수정·삭제할 수 있다.
- 치호 개인, 여자친구 개인, 공동 필터가 달력·목록·통계에서 일관된다.
- 카드 지출과 카드대금 납부가 중복 소비로 잡히지 않는다.
- 전체·부분 환불이 원 거래와 연결되고 실제 PostgreSQL 동시 요청에서도 초과 환불이 차단된다.
- 환불은 원 거래의 금융 bucket과 Account Entry 효과를 반대로 상속하고, 삭제 시 잔액·순소비·예산이 복원된다.
- active Refund가 있는 원 거래의 금융 edit/delete는 차단되고 환불 자체는 삭제 후 재생성한다.
- 월 예산 사용액이 거래와 일치한다.
- 반복 거래가 Household timezone과 DAILY/WEEKLY/MONTHLY/YEARLY schedule에 따라 canonical Transaction으로 중복 없이 생성된다.
- 월말·윤년 clamp, 지연 실행 catch-up, 동시 worker에서도 최초 anchor와 발생일별 멱등성이 보존된다.
- 설정에서 반복 규칙을 생성·수정·일시정지·재개할 수 있고 재개 시 일시정지 기간을 소급 생성하지 않는다.
- 자동 생성 거래가 달력·예산·통계·저축 활동에 일반 원장과 같은 값으로 반영되고 `반복` provenance가 표시된다.
- 결혼자금 현재 금액이 연결 Account와 일치한다.
- 결혼자금 Goal 생성·수정과 eligible Account 연결·해제가 current Household 경계에서 동작한다.
- 결혼자금 이번 달/6개월/완료 3개월 평균과 예상 상태가 Goal 경계 TRANSFER와 linked_at 기준에 일치한다.
- Goal 내부 이동, 연결 전 거래, INCOME/EXPENSE/REFUND를 신규 Goal 저축으로 중복 집계하지 않는다.
- concurrent Goal 생성·Account 연결·snapshot posting·target PATCH가 PostgreSQL 제약과 lock/version 계약을 지킨다.
- Home과 Goal 상세가 실제 read model 또는 정상 empty/error 상태를 표시하고 수동 Goal 기여금 action을 제공하지 않는다.
- Assets의 현재 Account 잔액, 총자산·총부채·순자산이 opening balance와 유효 Entry에서 파생되고 active·archived, 양수·0·음수를 그대로 포함한다.
- Assets의 actual Member PERSONAL/SHARED 소계는 Account ownership으로 귀속되고 합이 Household와 일치하며 다른 Household data를 포함하지 않는다.
- Assets가 Household timezone 직전 11개 완료 월말과 현재 한 점을 반환하고 opening date, logical delete, generated recurring 거래를 같은 원장 의미로 처리한다.
- Assets 화면이 canonical all/Member/shared URL, accessible 추이 표, loading/error/empty, Account Settings와 Quick Entry 경로를 제공한다.
- Settings에서 Household timezone 현재 월 기본 범위 또는 지정 기간의 current Household 거래 CSV를 내려받을 수 있다.
- CSV는 미삭제 Transaction당 한 row, 19개 한국어 고정 column, UTF-8 BOM, RFC 4180, 안정 정렬을 지킨다.
- REFUND/Recurring provenance와 archived reference를 유지하고 canonical Entry 손상은 fail-closed한다.
- 사용자/reference text의 formula prefix를 방어하며 foreign Household, `lastFour`, email, credential을 포함하지 않는다.
- PWA를 모바일 홈 화면에 설치할 수 있다.

## 품질

- 모든 재무 불변식 테스트 통과
- 다른 Household 접근 테스트 통과
- Access JWT 서명·issuer·audience·만료 검증 테스트 통과
- production profile에서 개발용 identity 우회가 비활성임을 검증
- Flyway clean database 적용 통과
- backend/frontend build와 lint/test 통과
- 핵심 모바일 E2E 통과
- API 응답과 로그에 secret·Access JWT·Access cookie·stack trace 없음

### Slice 10C-1 Immutable Runtime Harness Gate

- Java 25 Backend와 Node 24 Frontend가 multi-stage로 build되고 최종 image에 shell/package manager/build tool/source/test/cache가 남지 않는다.
- API와 Web runtime이 non-root로 실행되고 Web/API root filesystem은 read-only이며 capability와 privilege escalation이 차단된다.
- Nginx가 `/`와 SPA deep link를 정적 frontend로, `/api`와 `/api/**`를 Spring API로만 전달한다.
- Cloudflare Access JWT, original Host, forwarded address/proto, request ID가 API proxy에 전달되고 status/body/content type/CSV `Content-Disposition`을 숨기지 않는다.
- API/CSV와 `index.html`은 `no-store`, hashed asset은 immutable cache를 사용한다.
- `/actuator/**`는 public Nginx에서 404이고 `/healthz`는 backend/DB 세부정보가 없는 정적 응답이다.
- production profile에서 missing/blank Cloudflare/DB 설정이 fail-closed하고 forged local identity만으로 API에 접근할 수 없다.
- production Compose는 Web만 loopback port에 publish하고 API/DB host port, source bind mount, host network, privileged, Docker socket을 사용하지 않는다.
- disposable smoke에서 같은 candidate API image의 one-shot Flyway V1→V8/JPA validate 뒤 normal API readiness, restart schema history 유지, graceful stop과 resource residue 0을 검증한다.
- Hosted Full CI가 PR exact HEAD의 같은 runtime smoke를 통과한다.

### Slice 10C-2A Backup/Restore Safety Gate

- one-shot command가 absolute production Compose project, Git 밖 owner-only env file, dedicated owner-only backup directory를 요구하고 missing/relative/`..`/root/repository/Docker data/symlink/permission 오류를 fail closed한다.
- existing `postgres` service가 pinned PostgreSQL 18.6, running/healthy, project-scoped volume/internal network인지 확인하고 API/Web restart나 DB volume direct read 없이 online logical backup을 수행한다.
- `pg_dump` custom archive는 final 이름으로 노출되기 전에 nonzero, `PGDMP`, `pg_restore --list`, byte size와 SHA-256을 통과한다.
- dump, metadata, checksum은 owner-only atomic bundle 하나로 commit되고 같은 final 이름을 overwrite하지 않는다.
- `last-success.json`은 verified success 뒤에만 atomically 갱신되며 path/lock/pg_dump/integrity failure가 이전 marker와 valid bundle을 변경하지 않는다.
- metadata와 marker에는 timestamp, Flyway version, size, hash, artifact 이름, client/server version만 있고 secret/email/memo/재무 내용을 포함하지 않는다.
- synthetic source는 2 User/1 Household/2 Member, ASSET/SAVINGS/CREDIT_CARD, Category, INCOME/EXPENSE/TRANSFER/REFUND와 Budget/Recurring/Goal을 포함한다.
- empty target은 source와 다른 고유 Compose project/network/volume, host DB port 없는 PostgreSQL과 synthetic credential만 사용한다.
- restore는 checksum/metadata/archive 검증 뒤 `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`로 실행하고 warning/error를 성공으로 처리하지 않는다.
- restored target의 Flyway V1~V8, core row/Transaction/Entry/Refund lineage, Account balance·총자산·총부채·순자산이 source와 동일하다.
- restored target의 Household composite FK/unique가 계속 enforced되고 same-image migration rerun과 exact-HEAD normal production API의 JPA/readiness startup이 schema/data state를 바꾸지 않는다.
- zero/truncated/corrupt, checksum/metadata mismatch, missing project/service, stopped/unhealthy PostgreSQL, injected pg_dump failure와 restore target failure를 실제 gate에서 거부한다.
- 성공·실패 뒤 synthetic source/target/failure project의 container/network/volume과 unique API image tag residue가 0이다.
- Hosted Full CI가 PR exact HEAD에서 별도 backup/restore job을 실제 secret과 artifact upload 없이 통과한다.

### Slice 10C-2B1 Operational Status Harness Gate

- recurring scheduler는 process 시작, poll 시작/완료, top-level 성공/실패, advanced occurrence와 rule 단위 실패를 비식별 in-memory counter/timestamp로 기록하고 restart 시 reset된다.
- rule 하나의 생성 실패는 기존 격리와 다음 rule 진행을 유지하고 poll 자체가 정상 반환하면 operations 상태는 `UP`이며 raw failure count만 증가한다.
- top-level scheduler 예외는 `DOWN`으로 기록한 뒤 같은 예외 semantics를 유지하고 다음 성공 poll에서 consecutive execution failure count를 reset한다.
- `/actuator/health/operations`는 `recurringScheduler`만 details와 함께 제공하며 미실행/진행 중 `UNKNOWN`, 성공 `UP`, top-level 실패 `DOWN`을 사용한다.
- global health detail은 `never`를 유지하고 recurring signal은 liveness/readiness group에 포함되지 않으며 public Nginx `/actuator/**`는 계속 404다.
- Distroless API의 GET-only `HttpFetch`는 HTTP status/body와 transport failure를 구분하면서 기존 one-argument/HTTP 200 `HttpHealthCheck`를 바꾸지 않는다.
- `production-status.sh`는 strict project, Git 밖 owner-only env/backup path와 exact Compose labels를 요구하고 runtime/backup을 변경하지 않은 채 JSON object 하나만 출력한다.
- snapshot은 Web/API/PostgreSQL state/health/restart count, loopback origin status, recurring raw signal, verified backup freshness/inventory와 filesystem capacity만 exact allowlist로 포함한다.
- missing/stopped/unhealthy/unreachable, invalid/missing marker와 filesystem unavailable을 success로 위장하지 않으며 secret·email·금융 상세·container ID·absolute path를 포함하지 않는다.
- disposable smoke는 exact-HEAD image, 합성 backup/DB만 사용해 recurring success/rule failure/API unavailable/restart reset/public actuator 차단과 resource residue 0을 검증한다.
- Hosted Full CI가 PR exact HEAD에서 독립 observability job을 통과하며 threshold/evaluator/monitor/channel은 활성화하지 않는다.

### Slice 10C-2B2 Monitor/Alert Policy Harness Gate

- B1 canonical raw snapshot과 policy result가 분리되고 evaluator result/state/HomeOps payload에는 raw snapshot, secret, PII, 금융 상세, container/artifact/path identity가 없다.
- Web/API/PostgreSQL/recurring reachability는 target별 첫 failure를 `WARN`, 두 번째 연속 failure부터 `CRITICAL`로 평가하고 정상 observation에서 해당 streak만 reset한다.
- origin failure도 1회 `WARN`, 2회 `CRITICAL`이며 다른 service streak와 독립적이다.
- recurring poll 0은 process age 5분 미만 `STARTING/WARN`, 5분 이상 `CRITICAL`이고 completed poll age 5분 초과와 top-level failure를 `CRITICAL`로 평가한다.
- 같은 recurring completed poll은 rule failure streak를 중복 증가시키지 않고 새 failed poll 1~2회 `WARN`, 3회부터 `CRITICAL`, 새 clean poll에서 reset한다.
- verified local backup age 7시간 이상과 marker missing/invalid/unavailable은 `CRITICAL`, invalid/incomplete inventory는 `WARN`, foreign-only inventory는 status를 올리지 않는다.
- filesystem은 80% 이상 `WARN`, 90% 이상 또는 unavailable `CRITICAL`의 exact boundary를 지킨다.
- monitor state는 repository 밖 current-user owner mode `0700` directory와 `0600` state/lock file만 사용하고 temp fsync/atomic replace/directory fsync를 지킨다. state/backup/reporter canonical path는 pairwise disjoint다.
- corrupt/symlink/permissive/oversized state는 0으로 reset하지 않고 `STATE_INVALID/CRITICAL`로 fail closed하며 기존 bytes를 보존한다.
- concurrent monitor invocation은 non-blocking kernel lock으로 한 실행만 허용한다.
- HomeOps reporter는 repository/state/backup 밖 canonical regular non-symlink executable, current owner, group/other non-writable, exact `report-homeops-event.py` identity를 요구하고 validation failure를 lock/provider/reporter 호출 전에 거부한다.
- filesystem 사용률이 80% 미만에서 80% 이상으로 진입할 때 `DISK_LOW/ALERT`를 한 번 만들고 active episode 중 90% 진입은 새 event를 만들지 않는다. 80% 미만 회복은 같은 episode의 `RECOVERED`, 재진입은 새 episode key를 사용한다.
- pending payload는 reporter 호출 전에 atomic/fsync state에 저장하고 reporter exit 0 뒤에만 clear한다. nonzero/timeout/final state save failure는 같은 event key를 snapshot보다 먼저 재시도하며 shell, direct HTTP, HomeOps secret/origin/HMAC/spool 구현을 사용하지 않는다.
- service/origin/recurring/backup freshness/filesystem unavailable local signal은 evaluator result에 유지하되 HomeOps의 다른 signal type이나 lifecycle로 위장해 전달하지 않는다.
- retention dry-run plan은 latest verified 4개와 지난 7 KST day의 06:00 이후 첫 verified bundle을 keep하고 symlink/invalid/future/incomplete/foreign을 prune 후보에서 제외하며 어떤 artifact도 삭제하지 않는다.
- monitor plist는 60초, backup plist는 `00:35/06:35/12:35/18:35`, repository 밖 fixed bootstrap과 `KeepAlive` 부재를 고정하며 실제 install/load를 실행하지 않는다.
- Hosted Full CI가 PR exact HEAD에서 독립 `monitor-policy` job을 통과하고 actual production HomeOps reporter/spool/API, notification, LaunchAgent/backup/offsite를 활성화하지 않는다.

### Slice 10D-1 Immutable Release/Deploy Source Harness Gate

- `main` push와 controlled manual dispatch가 같은 재사용 Full CI를 먼저 실행하며 production concurrency는 `our-ledger-production`, `cancel-in-progress: false`로 직렬화된다.
- `OUR_LEDGER_DEPLOY_ENABLED`가 없거나 정확히 `true`가 아니면 validation만 실행되고 GHCR login/publish, Tailscale, SSH와 production environment job은 시작하지 않는다.
- API와 Web은 같은 exact 40자리 commit SHA tag, `linux/arm64`, OCI source/revision/version label로만 publish하도록 정의하며 `latest`와 임의 image/tag를 허용하지 않는다.
- runtime config는 `scratch` 기반 secret-free artifact이며 `compose.prod.yaml`, Nginx 설정과 공개 host-side 운영 script의 exact allowlist를 regular file별 `0600`/`0700` mode로 포함한다. 자동 생성 parent directory mode는 artifact contract가 아니며 host owner/directory mode는 10D-2B1 state primitive와 10D-3 설치 단계가 강제한다.
- last successful Production revision과 candidate의 runtime source diff가 없으면 `keep`, 변경·첫 bootstrap·명시적 force면 `update`를 반환하고 missing/non-ancestor/invalid range는 fail closed한다.
- restricted transport command는 `deploy-our-ledger-v1 <sha> keep <actor>` 또는 `deploy-our-ledger-v1 <sha> update <sha256:64hex> <actor>` 두 grammar만 허용하고 caller가 shell, path, image name 또는 추가 argument를 주입할 수 없다.
- GHCR token은 restricted SSH command의 표준 입력으로만 전달되고 command argument, environment 확장 값, log 또는 runtime-config artifact에 포함되지 않는다.
- publish/deploy privileged job의 모든 third-party action ref는 exact 40자리 commit SHA다.
- local source gate가 helper unit test, detector range, workflow kill switch/permissions/grammar와 secret-free runtime-config file tree/mode/label/Compose render를 synthetic하게 검증한다.
- Hosted Full CI가 PR exact HEAD에서 release-transport gate를 통과하며 actual GHCR, Tailscale, SSH, Mac mini, production backup/migration/deploy 또는 secret을 사용하지 않는다.
- 10D-1 완료는 transport source contract만 뜻한다. B1 lock/state와 B2 restricted transaction source가 후속 gate로 추가됐어도 actual host install, credential·Cloudflare·schedule·public activation은 10D-3 별도 승인 전까지 존재하거나 활성화됐다고 간주하지 않는다.

### Slice 10D-2A Candidate Migration/Validation Gate

- normal `production` profile은 `spring.flyway.enabled=false`, JPA `ddl-auto=validate`, bootstrap false, recurring scheduler true이며 clean schema를 생성하지 않고 fail closed한다.
- profile-gated `api-migration`은 normal API와 동일한 exact candidate image, production datasource와 application/database network를 사용하고 host port 없이 disposable `--rm` one-shot으로 실행된다.
- migration mode는 `production,migration`, Flyway enabled, JPA validate, Web application type `NONE`, bootstrap/scheduler false를 강제하고 local/test 혼합이나 설정 override를 nonzero로 거부한다.
- Flyway migrate와 candidate entity model validation이 모두 성공한 뒤에만 고정된 비민감 marker를 한 번 출력하고 deterministic exit 0을 반환한다. Flyway/JPA/DB/profile failure는 nonzero다.
- clean DB V1→V8, 같은 DB idempotent rerun, failed Flyway history, synthetic schema damage, unreachable DB와 invalid profile/flag를 actual PostgreSQL/container process에서 검증한다.
- migration mode는 HTTP listener, recurring poll/occurrence와 User/Household bootstrap write를 만들지 않고, rerun 전후 financial fixture와 schedule cursor가 동일하다.
- normal API의 unmigrated DB failure와 migrated DB startup/restart를 함께 검증하고 Flyway history/checksum이 normal lifecycle에서 바뀌지 않는다.
- V1~V8 migration filename과 byte SHA-256을 repository gate로 고정하고 신규 V9 또는 기존 migration 수정 없이 backup/restore와 observability smoke를 같은 one-shot 순서로 실행한다.
- 성공·실패 cleanup 뒤 exact synthetic project container/network/volume/image residue가 0이며 credential/token/email을 output evidence로 노출하지 않는다.
- Hosted Full CI가 PR exact HEAD에서 전체 gate를 통과하고 actual production/GHCR/Tailscale/SSH/HomeOps/Cloudflare를 사용하지 않는다.

### Slice 10D-2B1 Host State / Shared Operation Lock / Runtime-config Staging Gate

- production worker의 app root는 `/Users/homeserver/Server/apps/our-ledger`로 고정하고 production CLI/environment에 `--root`, `--app-dir`, state/Compose path override 또는 public lock bypass를 노출하지 않는다.
- `operations/lock`은 current owner mode `0700` atomic directory 하나이며 첫 holder만 성공하고 두 번째 holder, stale directory, symlink, unexpected lock entry는 즉시 fail closed한다. PID 기반 stale cleanup과 lock stealing은 없다.
- public standalone backup wrapper와 B2 deploy transaction이 같은 project lock authority를 사용하고, lock을 가진 deploy가 non-executable internal backup core를 직접 호출할 수 있어 nested self-deadlock이 없다.
- runtime-config release path는 exact `sha256:<64 lowercase hex>`에서만 `releases/<digesthex>`로 파생하고 exact regular-file/directory allowlist, `0600`/`0700`, current owner와 hardlink/symlink/nonregular/unexpected entry 금지를 검증한다.
- 같은 digest와 같은 content는 reuse하고 같은 digest의 다른 content는 overwrite하지 않는다. source path가 release destination을 정하거나 immutable release를 교체할 수 없다.
- `current`는 verified release를 향하는 relative symlink만 허용하고 temp symlink→atomic replace→directory fsync로 갱신한다. absolute/external/dangling/corrupt target은 fail closed한다.
- `state/deployment.json`과 `pending/transaction.json`은 B2 phase/schema evidence를 포함한 formatVersion 2 exact schema, mode `0600`, secret/PII 부재, temp write→file fsync→atomic replace→directory fsync를 지킨다. production activation 전 source이므로 formatVersion 1 compatibility shim이나 migration은 제공하지 않고 구버전을 fail closed한다.
- pending 존재 중 새 stage/transaction은 거부하고 crash 뒤 pending을 보존한다. candidate 성공을 추측하지 않으며 explicit abandoned pending clear는 current/state가 previous에서 변하지 않은 경우만 허용한다.
- local `verify-host-state.sh`와 synthetic backup/restore gate는 temp app root/disposable Compose만 사용해 lock contention, release reuse/collision, corruption/path escape, pending/crash와 internal core 호출을 검증한다.
- runtime-config Dockerfile, change detector, exported file/mode gate와 Hosted Full CI 독립 `host-state` job이 동기화되고 actual `/Users/homeserver/Server`, GHCR/Tailscale/SSH/HomeOps/production resource를 읽거나 쓰지 않는다.
- 10D-2B1 primitive는 B2 transaction에서 재사용하며 actual host install/dry run과 activation은 10D-3 전까지 수행하지 않는다.

### Slice 10D-2B2 Restricted Host Deployment Transaction Gate

- production entrypoint는 `SSH_ORIGINAL_COMMAND`의 기존 keep/update grammar와 stdin token만 받으며 root, Compose, image, reporter, backup 또는 skip override를 노출하지 않는다.
- verified current가 없는 fresh host는 keep/update 모두 거부한다. API/Web/runtime-config repository와 Mac mini app/env/backup/reporter/loopback authority는 source 상수로 고정한다.
- API/Web은 requested exact SHA tag, linux/arm64, expected repository, valid image ID/repository digest와 OCI source/revision/version을 모두 만족해야 writer를 멈춘다. runtime update는 command의 exact digest와 exported exact allowlist/mode를 다시 검증한다.
- shared operation lock 아래 `writer quiesce → verified predeploy backup → pre-schema authority → same-image migration marker → post-schema authority → same-SHA API/Web cutover → postgres/API/Web/loopback readiness → env/current/state commit` 순서를 건너뛰지 않는다.
- Flyway successful version, failed count 0과 deterministic history fingerprint를 pending에 durable하게 기록한다. migration 뒤 authority가 달라진 failure에는 previous image나 DB restore/reverse migration을 자동 실행하지 않고 pending을 보존해 operator intervention으로 종료한다.
- schema authority가 같을 때만 previous image pair를 복구하고 exact image env 두 key만 file fsync→atomic replace→parent fsync로 갱신한다. `down --volumes`, broad prune, caller shell/path/image와 public smoke는 사용하지 않는다.
- pending formatVersion 2 phase는 skipped transition을 거부한다. pre-migration, post-migration, cutover, readiness와 current/state/pending commit crash를 observed runtime/schema/readiness와 함께 deterministic하게 복구하거나 fail closed한다.
- HomeOps에는 actual receiver vocabulary `RUNNING`, `SUCCESS`, `FAILED`, `ROLLED_BACK`와 bounded non-sensitive lifecycle만 `[reporter, "deployments"]` JSON stdin으로 전달한다. reporter nonzero/timeout은 application outcome을 바꾸지 않고 secret/origin/HMAC/spool을 직접 다루지 않는다.
- `verify-host-deploy-transaction.sh`의 32개 synthetic test는 실제 GHCR, Docker daemon, Tailscale, SSH, Mac mini, production path/service/backup/migration, HomeOps 또는 public network를 호출하지 않는다.
- Hosted Full CI가 PR exact HEAD에서 독립 `host-deploy-transaction` job과 기존 전체 gate를 통과한다. 이 완료는 source 검증일 뿐 install, credential, kill switch 활성화, release/deploy 또는 public acceptance가 아니다.

## 운영

- Mac mini Docker Compose 배포 성공
- 외부 공개 경로는 Cloudflare Access + Cloudflare Tunnel 사용
- Cloudflare Access Allow 정책이 실제 사용자 두 이메일로 제한됨
- `cloudflared` Access JWT 검증이 활성화됨
- Access를 우회해 origin에 접근 가능한 공용 경로가 없음
- DB 포트 직접 공개 없음
- 자동 backup 성공 확인
- 별도 환경에서 restore drill 1회 성공
- health check와 승인된 운영 monitor 확인

위 운영 항목 중 Mac mini deploy, 실제 artifact publish, Access/Tunnel, production DB/secret/User, production status/backup/migration/restore/HomeOps reporter와 LaunchAgent는 10D-2B2 완료 기준이 아니다. B2는 host transaction source의 합성 검증까지만 제공하며 install/credential·public route·schedule·retention 삭제·age/iCloud 외부복제·production restore는 10D-3 또는 별도 HomeOps extension에서 승인한다.

## 문서

- API, ERD, 인증, 인가, 운영 문서가 실제 구현과 일치
- production 환경 변수 목록과 secret 주입 방식 기록
- 미결정 운영 정책이 production gate 전에 해소
