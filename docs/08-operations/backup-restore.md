---
status: active
version: 0.4
last_updated: 2026-08-29
related:
  - 03-data/data-retention.md
  - 07-quality/acceptance-criteria.md
---

# 백업과 복구

## 현재 상태

Slice 10C-2A는 scheduler에서 호출 가능한 host one-shot command, PostgreSQL custom-format atomic artifact, checksum/metadata/latest-success contract와 synthetic isolated restore drill을 구현한다.

실제 Mac mini production backup/restore는 실행하지 않았고 schedule, retention 삭제, 외부 destination/암호화 복제도 활성화하지 않았다. source/CI gate 통과는 production disaster recovery 준비 완료가 아니다.

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
- secret과 backup 파일은 Git, log, GitHub Actions artifact에 저장하지 않는다.

### Atomic artifact

세 개 파일을 하나의 owner-only partial directory 안에 만들고 file/directory fsync 뒤 directory 자체를 final `.backup` 이름으로 rename한다.

```text
our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.backup/
├─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.dump
├─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.json
└─ our-ledger_production_20260829T031500Z_v8_a1b2c3d4e5f6.sha256
```

metadata field는 `formatVersion`, `createdAt`, `schemaVersion`, `sizeBytes`, `sha256`, `dumpFilename`, `pgDumpVersion`, `postgresServerVersion`로 고정한다. email, memo, Category/Account 내용, DB password, Cloudflare credential, full Compose config와 absolute host path는 포함하지 않는다.

`last-success.json`은 같은 비민감 metadata와 `bundleDirectory`만 담는다. verified bundle commit 뒤 temporary owner-only file에서 atomic replace하며 failed backup은 이전 marker를 덮어쓰지 않는다.

### One-shot command

```bash
./scripts/backup-production.sh \
  --project-name <exact-production-compose-project> \
  --env-file <absolute-owner-only-file-outside-repository> \
  --backup-dir <absolute-dedicated-owner-only-directory>
```

command는 exact repository `compose.prod.yaml`, project/config/image label, PostgreSQL running/healthy, project-scoped volume/internal network와 Flyway successful version을 확인한다. stdout에는 final artifact path, UTC timestamp와 schema version만 출력한다. failure는 nonzero exit다.

동일 backup directory의 concurrent 실행은 lock directory로 차단한다. stale lock은 실행 중인 backup과 partial/final/marker 상태 확인 없이 자동 제거하지 않는다.

## 보관기간

정확한 일·주·월 보관 개수는 production gate에서 저장공간, RPO/RTO, 외부복제와 파기 정책을 기준으로 확정한다. 10C-2A inventory helper는 strict valid/invalid/incomplete/foreign artifact를 분류만 하고 삭제하지 않는다. 자동 prune는 확정 전 실행 보류 항목이다.

## Restore Drill

`./scripts/verify-backup-restore.sh`는 실제 production resource 없이 다음을 검증한다.

1. exact-HEAD production API image를 build한다.
2. 고유 source Compose project/volume의 PostgreSQL에 API Flyway V1→V8을 적용한다.
3. 2 User/1 Household/2 Member, ASSET/SAVINGS/CREDIT_CARD, Category, INCOME/EXPENSE/TRANSFER/REFUND, Budget/Recurring/Goal synthetic fixture를 넣는다.
4. one-shot command로 실제 custom backup bundle을 만든다.
5. source와 다른 고유 target project/network/volume의 empty PostgreSQL에 `pg_restore --exit-on-error --single-transaction --no-owner --no-acl`로 복구한다.
6. Flyway versions, core table row count, Transaction/Entry/Refund lineage, Account balance와 total asset/liability/net worth를 source fingerprint와 비교한다.
7. composite Household FK와 unique constraint가 계속 enforced되는지 확인한다.
8. restored DB에 production API image를 연결해 Flyway/JPA validate/readiness를 통과하고 state가 변하지 않는지 확인한다.
9. success/failure 뒤 source/target/failure container/network/volume과 unique image tag residue 0을 확인한다.

missing/unsafe path, missing project/service, stopped/unhealthy DB, collision/lock, injected pg_dump failure, zero/truncated/corrupt archive, checksum/metadata mismatch와 restore target failure를 성공으로 처리하지 않는다. backup 성공 로그만으로 복구 가능성을 주장하지 않는다.

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
- 10C-2A source/drill은 구현됐지만 production backup/restore 실행과 보관·외부복제 정책 확정은 10D의 별도 운영 Gate다.
