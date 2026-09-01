---
status: active
version: 0.9
last_updated: 2026-09-01
related:
  - 03-data/data-retention.md
  - 07-quality/acceptance-criteria.md
---

# 백업과 복구

## 현재 상태

Slice 10C-2A는 scheduler에서 호출 가능한 host one-shot command, PostgreSQL custom-format atomic artifact, checksum/metadata/latest-success contract와 synthetic isolated restore drill을 구현한다. Slice 10C-2B2는 실제 삭제 없는 recent4+daily7 retention plan과 future `:35` schedule/offsite freshness 계약을 확정한다. Slice 10D-1의 secret-free runtime-config artifact는 이 공개 backup source를 immutable allowlist로 운반하고, Slice 10D-2A는 source/restore target에 동일 candidate image의 migration/JPA validation one-shot을 적용하도록 drill 순서를 보정한다. Slice 10D-2B1은 public standalone wrapper의 project operation lock과 lock을 다시 얻지 않는 internal backup core를 분리해 future deploy의 nested self-deadlock을 제거한다. Slice 10D-2B2 transaction source는 current API writer를 멈춘 뒤 같은 shared lock을 유지하며 internal core 성공과 pre-schema authority를 확인한 경우에만 candidate migration을 시작한다. Slice 10D-3A1의 Household bootstrap source는 backup을 대신하거나 backup artifact에 input/PII를 저장하지 않는다. Slice 10D-3A2 fresh-host source는 normal readiness 뒤 같은 shared lock에서 internal core로 최초 verified backup과 marker hash를 확인한 후에만 input 소비와 current/state commit을 허용한다. Slice 10D-3B3A는 verified local bundle만 읽는 age encrypted offsite worker, atomic marker, 8시간 freshness와 synthetic decrypt gate를 source에 추가한다. Slice 10D-3B3C bridge는 old worker 호환을 위해 offsite wrapper/worker를 runtime artifact에서 일시 제외했고, Slice 10D-3B3F source가 strict V2 manifest에 두 파일을 다시 포함한다. V2 release/publish/host update, host 설치, production backup/migration/bootstrap/offsite 실행, schedule 또는 retention 삭제는 활성화하지 않는다.

실제 Mac mini production backup/restore는 실행하지 않았고 LaunchAgent, retention 삭제, age recipient/iCloud 복제와 central freshness incident도 활성화하지 않았다. source/CI gate 통과는 production disaster recovery 준비 완료가 아니다.

## 목표

단일 Mac mini와 단일 PostgreSQL은 장애 시 데이터 손실 가능성이 있다. backup은 같은 디스크의 복사본만으로 끝내지 않는다.

## Backup

- existing healthy production Compose의 `postgres` container 안 PostgreSQL 18.6 `pg_dump`를 사용한다.
- `--format=custom --no-acl` archive를 online 생성하고 API/Web을 restart하지 않는다.
- DB password를 새 command-line argument로 만들지 않고 container의 기존 environment를 사용한다.
- production DB volume을 mount/copy/tar하거나 Docker socket을 application container에 mount하지 않는다.
- filename은 고정 product/environment prefix, UTC second, successful Flyway version과 random collision suffix만 사용한다.
- `umask 077`, owner-only env/directory/file과 strict absolute path confinement를 요구한다.
- final 공개 전 nonzero, `PGDMP` magic, `pg_restore --list`, byte size, SHA-256과 metadata consistency를 확인한다.
- shell redirection이 만든 owner-only regular `.dump`를 staging directory `dir_fd`와 `lstat`/`fstat`로 재검증하고 해당 file descriptor에 `fsync`한 뒤에만 archive 검증과 publish를 계속한다.
- backup 전후 한 statement로 읽은 Flyway failed migration count가 모두 0이고 latest successful version이 동일할 때만 pre-check version을 filename/metadata에 사용한다.
- secret과 backup 파일은 Git, log, GitHub Actions artifact에 저장하지 않는다.

### Atomic artifact

세 개 파일을 하나의 owner-only partial directory 안에 만든다. `pg_dump` file descriptor, metadata/checksum file과 partial directory를 순서대로 fsync한 뒤 directory 자체를 final `.backup` 이름으로 rename한다.

```text
our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.backup/
├─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.dump
├─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.json
└─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.sha256
```

metadata field는 `formatVersion`, `createdAt`, `schemaVersion`, `sizeBytes`, `sha256`, `dumpFilename`, `pgDumpVersion`, `postgresServerVersion`로 고정한다. email, memo, Category/Account 내용, DB password, Cloudflare credential, full Compose config와 absolute host path는 포함하지 않는다.

`last-success.json`은 같은 비민감 metadata와 `bundleDirectory`만 담는다. verified bundle commit 뒤 temporary owner-only file에서 atomic replace하며 failed backup은 이전 marker를 덮어쓰지 않는다.

Slice 10C-2B1의 `production-status.sh`는 이 marker와 strict inventory를 backup freshness의 유일한 source로 read-only 관측한다. marker가 없거나 marker/bundle 계약이 invalid하면 현재 시각을 성공 시각으로 채우지 않고 `MISSING/INVALID`를 반환한다. status command는 backup write probe, `pg_dump`, cleanup 또는 marker 갱신을 호출하지 않으며 artifact 이름·hash·absolute backup path를 snapshot에 복사하지 않는다.

### One-shot command

```bash
./scripts/backup-production.sh \
  --project-name <exact-production-compose-project> \
  --env-file <absolute-owner-only-file-outside-repository> \
  --backup-dir <absolute-dedicated-owner-only-directory>
```

public command는 fixed production app root의 B1 host worker를 통해 shared project operation lock을 먼저 얻고, pending recovery가 없을 때만 non-executable internal core를 호출한다. core는 exact runtime-config release의 artifact 이름 `compose.yaml`, project/config/image label, PostgreSQL running/healthy, project-scoped volume/internal network를 확인한다. `pg_dump → dump fsync → pg_restore --list → Flyway post-check → sidecar/hash → partial directory fsync → final rename → backup directory fsync → last-success atomic replace → backup directory fsync` 순서로 publish한다. stdout에는 final artifact path, UTC timestamp와 schema version만 출력한다. failure는 nonzero exit다.

backup window 전후 successful Flyway version이 같고 failed migration count가 모두 0인 경우에만 artifact를 publish한다. version 변화나 failed row를 감지하면 sidecar/final bundle을 만들지 않고 partial을 폐기하며 기존 `last-success.json`을 유지한다. shared project lock은 B1/B2가 관리하는 deploy와 standalone backup을 직렬화하고, pre/post Flyway gate는 lock authority 밖의 예기치 않은 migration overlap까지 성공으로 인정하지 않는 fail-closed 방어다.

deploy와 standalone backup의 concurrent 실행은 fixed app root의 `operations/lock` atomic directory 하나로 차단한다. lock은 current owner mode `0700`, non-blocking이며 stale lock을 PID만 보고 자동 제거하거나 steal하지 않는다. public `--skip-lock`과 environment bypass는 없다. internal core는 public 진입점이 아니고 future deploy가 이미 shared lock을 가진 상태에서만 직접 호출한다.

B2 deploy의 backup ordering은 `candidate artifact 검증 → current API quiesce → lock-held backup_core.sh → verified final bundle/marker → Flyway authority snapshot → migration`이다. quiesce 실패면 backup과 migration을 모두 시작하지 않고, backup 실패면 migration/cutover를 시작하지 않는다. 이 경로도 기존 dump fsync, pre/post Flyway overlap check, exact 3-file bundle, atomic marker와 previous marker 보존 계약을 바꾸지 않는다. schema가 바뀐 post-migration failure에는 backup을 자동 restore하지 않으며 pending evidence를 보존해 operator intervention으로 종료한다.

## 보관기간

accepted dry-run policy는 다음과 같다.

- recent: 최신 verified snapshot 4개
- daily: 지난 7 KST calendar day마다 06:00 이후 첫 verified snapshot 1개
- recent/daily 중복 제거
- 나머지 verified snapshot만 `pruneCandidates`
- invalid/future, incomplete, foreign과 symlink는 삭제 후보에서 제외

`backup_artifact.py retention-plan`은 strict inventory에서 deterministic JSON의 `keep`, `pruneCandidates`, `invalidIgnored`, `incompleteIgnored`, `foreignIgnored`만 계산한다. artifact, marker와 backup directory를 쓰거나 삭제하지 않는다.

```bash
python3 scripts/backup_tools/backup_artifact.py retention-plan \
  --backup-dir <absolute-dedicated-owner-only-directory>
```

최소 7일 운영 관찰, offsite decrypt 성공, isolated restore drill 성공과 별도 production deletion 승인 전에는 `pruneCandidates`를 삭제하지 않는다. `rm -rf` 기반 prune와 이름/age만 본 삭제는 허용하지 않는다.

## Encrypted offsite source와 schedule activation 경계

`launchd/com.homeserver.our-ledger-backup.plist.example`은 Mac mini local timezone에서 `00:35`, `06:35`, `12:35`, `18:35`에 repository 밖 fixed bootstrap을 호출한다. `launchd/com.homeserver.our-ledger-offsite.plist.example`은 committed backup window 뒤 `00:50`, `06:50`, `12:50`, `18:50`에 fixed offsite bootstrap의 `run`만 호출한다. 둘 다 `KeepAlive`와 private identity environment를 사용하지 않는다. plist나 fixed ingress를 설치·load/start하지 않았으며 실제 schedule은 10D-3B의 별도 운영 승인이다.

repository source의 `scripts/offsite-backup-production.sh` public interface는 fixed production authority에서 `run`과 read-only `status`만 허용한다. path나 executable override는 없다. 이 wrapper와 worker는 Manifested V2 source artifact의 declared payload에 포함되지만 V2 artifact가 별도 release·publish·host update되기 전에는 production command로 사용할 수 없다. future actual public config authority는 repository 밖 `/Users/homeserver/Server/apps/our-ledger/offsite.env` regular file 하나이며 current owner, mode `0600`, link count 1을 요구한다. 이 파일은 public `AGE_RECIPIENT`와 canonical iCloud project target `ICLOUD_TARGET_DIRECTORY`만 포함하고 private identity를 허용하지 않는다. state directory는 repository 밖 owner-only `offsite-state`, production encryptor는 `/opt/homebrew/bin/age`, tar는 `/usr/bin/bsdtar`로 고정한다. 이 path와 값은 source 계약일 뿐 이번 gate에서 생성하거나 읽지 않는다.

worker transaction은 다음 순서를 따른다.

```text
fixed config/path/binary + strict latest marker/bundle 검증
→ matching marker/final이면 exact hash 확인 뒤 NO_OP
→ owner-only local ciphertext staging
→ verified bundle 전체의 bsdtar stdout을 age public recipient로 암호화
→ staging file fsync + nonzero + SHA-256
→ project-specific iCloud .partial copy + fsync + SHA-256 비교
→ local source authority 재검증
→ native atomic no-replace final publish + target directory fsync
→ final regular-file/size/SHA-256 및 source 재검증
→ offsite-last-success.json temp fsync + atomic replace + directory fsync
→ invocation-owned local staging cleanup
```

plaintext tar file과 raw PostgreSQL dump를 offsite/staging에 만들지 않는다. final publish는 macOS의 `renamex_np(RENAME_EXCL)`, Linux CI의 `renameat2(RENAME_NOREPLACE)`만 사용하며 check-then-rename이나 overwrite fallback을 허용하지 않는다. finalization 순간 destination이 생기거나 native primitive가 없으면 nonzero로 끝나고 경쟁 destination의 bytes/inode, 기존 valid final/marker와 unrelated target entry를 보존한다. source가 처리 중 변경되거나 config/binary/path/marker/bundle/tar/age/fsync/copy/hash/rename/final 검증이 실패해도 같은 fail-closed 계약을 지키며, worker는 이번 invocation이 만든 exact staging/partial/final만 identity 확인 후 rollback할 수 있고 broad cleanup이나 retention 삭제를 하지 않는다. final publish 뒤 marker commit 전에 crash하여 marker 없는 collision이 남으면 randomized ciphertext를 덮어쓰거나 성공으로 추측하지 않고 operator 분류가 필요한 fail-closed 상태다.

marker는 source logical bundle/createdAt/schema, replicatedAt, ciphertext filename/size/SHA-256만 저장한다. 같은 latest source의 marker와 final hash가 정확히 일치할 때만 새 randomized ciphertext를 만들지 않고 `NO_OP`한다. `status`는 marker/final을 쓰지 않고 검증해 `MISSING`, `INVALID`, `FRESH`, `STALE`, age와 8시간 grace만 privacy-safe JSON으로 노출한다. local verified backup grace는 계속 7시간이다. HomeOps에는 offsite freshness type이 없으므로 다른 signal로 위장하지 않으며 central typed alert는 별도 HomeOps extension이다.

`./scripts/verify-offsite-backup.sh`는 disposable owner-only directory와 pinned age v1.3.1만 사용해 actual encrypt/decrypt tar round-trip, source file hash 재현, no-op/new latest, 8시간 freshness, config/path/source/collision과 tar/age/timeout/fsync/copy/hash/rename/marker failure preservation을 검증한다. Linux CI download는 official archive URL과 architecture별 SHA-256을 고정하며 curl-pipe-shell을 사용하지 않는다. 실제 production path, iCloud, recipient, LaunchAgent, DB/Compose와 private identity는 사용하지 않고 test identity는 temporary directory 종료와 함께 제거한다.

## Restore Drill

`./scripts/verify-backup-restore.sh`는 실제 production resource 없이 다음을 검증한다.

1. exact-HEAD production API image를 build한다.
2. 고유 source Compose project/volume의 PostgreSQL에 동일 candidate API image one-shot으로 Flyway V1→V8과 JPA validate를 적용한 뒤 normal API를 시작한다.
3. 2 User/1 Household/2 Member, ASSET/SAVINGS/CREDIT_CARD, Category, INCOME/EXPENSE/TRANSFER/REFUND, Budget/Recurring/Goal synthetic fixture를 넣는다.
4. one-shot command로 실제 custom backup bundle을 만든다.
5. source와 다른 고유 target project/network/volume의 empty PostgreSQL에 `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`로 복구한다.
6. Flyway versions, core table row count, Transaction/Entry/Refund lineage, Account balance와 total asset/liability/net worth를 source fingerprint와 비교한다.
7. composite Household FK와 unique constraint가 계속 enforced되는지 확인한다.
8. restored V8 DB에 동일 candidate migration mode를 재실행해 idempotent exit 0과 state 불변을 확인하고, normal production API의 Flyway-disabled JPA validate/readiness를 통과한다.
9. success/failure 뒤 source/target/failure container/network/volume과 unique image tag residue 0을 확인한다.

missing/unsafe path, missing project/service, stopped/unhealthy DB, collision/lock, injected pg_dump/dump fsync failure, Flyway version change/post-check failed migration, zero/truncated/corrupt archive, checksum/metadata mismatch와 restore target failure를 성공으로 처리하지 않는다. backup 성공 로그만으로 복구 가능성을 주장하지 않는다.

### Production restore Gate

disposable drill command를 production DB에 사용하지 않는다. 실제 사고 복구는 write freeze, 사고 시점, latest verified local/external backup, 원본 보존, 별도 restore 검증, RPO 누락 범위, exact target, application compatibility, rollback을 확인한 별도 승인 작업이다.

production DB를 drop/recreate하거나 `docker compose down --volumes`하는 command는 이 source에 제공하지 않는다.

## 복구 우선순위

1. production 쓰기 중지
2. 사고 시점과 최신 정상 backup 확인
3. 원본 보존
4. 별도 환경 restore 검증
5. 복구 대상 시점 확정
6. production 교체
7. application/schema compatibility와 readiness 확인
8. 사용자에게 누락 가능 기간 명시

## CSV

사용자 CSV export는 운영 backup의 대체물이 아니다. CSV는 데이터 이동성과 수동 확인을 위한 기능이다.

- CSV는 지정 기간의 미삭제 Transaction과 최소 reference/provenance만 포함하며 schema, Flyway history, 논리삭제 row, 운영 설정을 복구하지 못한다.
- CSV 성공은 `pg_dump`, 외부 보관, retention, restore drill 성공을 의미하지 않는다.
- 서버는 CSV history나 temp file을 backup처럼 보관하지 않는다.
- 10C-2A source/drill, 10D-1 immutable transport, 10D-2A candidate migration, 10D-2B1 shared lock/state, 10D-2B2 deployment transaction, 10D-3A1/A2 bootstrap, 10D-3B3A encrypted offsite source, 10D-3B3C evolution bridge와 10D-3B3F V2 artifact source gate는 구현됐지만 V2 release·publish·host update, production backup/migration/bootstrap/restore/offsite 실행과 host ingress/install·schedule·보관·외부복제 활성화는 별도 운영 Gate다.
