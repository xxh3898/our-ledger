---
status: active
version: 2.0
last_updated: 2026-09-01
related:
  - 01-product/feature-matrix.md
  - 07-quality/acceptance-criteria.md
  - ADR-008
  - ADR-009
---

# 개발 로드맵

ERD는 V1 전체를 미리 설계하지만 구현과 migration은 Vertical Slice 단위로 진행한다.

| Slice | 목표 | 출시 가능한 결과 |
|---|---|---|
| 0. Foundation | Java/Spring/React/PostgreSQL/Flyway/Docker/CI bootstrap | 로컬·CI에서 health check 성공 |
| 1. Auth/Household | Cloudflare Access identity 검증, 내부 User 매핑, 사용자 2명, Household 경계 | Access 인증 후 내부 User/Household 진입 가능 |
| 2. Basic Ledger | Account, Category, 수입·지출, 빠른 입력, 목록 | 실제 가계부 최소 사용 가능 |
| 3. Transfer/Card | Account Entry, 이체, 신용카드, 카드대금 | 잔액·부채 계산 가능 |
| 4. Calendar | 월 달력, 일별 내역, 개인/공동 필터 | Weple형 메인 사용 흐름 완성 |
| 5. Budget | 전체·개인·공동·카테고리 예산 | 월 예산 관리 가능 |
| Pre-6 Refund Gate | 전체·부분 환불, 누적 상한, 원 거래 lineage 보호 | Statistics가 신뢰할 환불 원장 완성 |
| 6. Statistics | 기간·카테고리·주체·전월 비교 | 소비 분석 가능 |
| 7. Recurring | 월급·구독·적금 자동 생성 | 반복 입력 감소 |
| 8. Marriage Goal | Goal/Account 연결, 달성률·예상일 | 결혼자금 추적 가능 |
| 9. Assets | 자산·부채·순자산·월 추이 | 재무 상태 확인 가능 |
| 10A. CSV Export | 기간 지정 원장 CSV, spreadsheet 안전성 | Settings에서 검산·이동용 CSV 다운로드 |
| 10C-1. Immutable Runtime Harness | multi-stage image, Nginx, production profile/Compose, smoke | 실제 secret 없는 production origin 검증 |
| 10C-2A. Backup/Restore Safety Gate | custom backup, integrity metadata, disposable restore | 합성 데이터의 재현 가능한 복구 검증 |
| 10C-2B1. Operational Status Harness | health, backup freshness, recurring/filesystem raw signal | privacy-safe read-only snapshot 검증 |
| 10C-2B2. Monitor/Alert Policy | threshold, evaluator, state와 HomeOps reporter 경계 | 합성 정책 검증, 실제 감시는 10D에서 활성화 |
| 10B. PWA Installability | manifest, service worker, production icon | 최종 이름·icon 결정 뒤 모바일 홈 화면 설치 가능 |
| 10D-1. Immutable Release/Deploy Source | Full CI 재사용, exact-SHA artifact, restricted intent | 기본 비활성 source/CI harness 검증 |
| 10D-2A. Candidate Migration/Validation Gate | normal startup mutation 제거, same-image one-shot Flyway/JPA gate | disposable DB에서 migration/cutover 선행조건 검증 |
| 10D-2B1. Host State / Shared Operation Lock / Runtime-config Staging | 고정 host root, project lock, immutable release와 versioned state source | temp host synthetic gate 검증 |
| 10D-2B2. Host Deployment Transaction | restricted wrapper, backup/migration/cutover/readiness/recovery 조합 | pure/synthetic source gate 검증, 실제 설치는 10D-3B |
| 10D-3A1. Production Household Bootstrap One-shot Gate | same-image no-HTTP exact-state bootstrap protocol | 합성 DB에서 create/verify/fail-closed source 검증 |
| 10D-3A2. Fresh-host Bootstrap Transaction Source | owner-only input, fixed ingress, migration/bootstrap/backup durable transaction | 실제 값 없는 fresh-host source 검증 |
| 10D-3B0. Exact-SHA GHCR Publish-only Source | main/run authority, digest-first artifact, exact tag conflict gate | deploy와 분리된 수동 publish source 검증 |
| 10D-3B3A. Encrypted Offsite Backup Source | verified bundle, age stream, iCloud atomic publish, freshness | 실제 recipient/iCloud 없는 synthetic source 검증 |
| 10D-3B3C. Runtime-config Evolution Bridge | frozen Legacy V1 bridge, strict Manifested V2 validator | old worker 호환 bridge와 후속 V2 전환 source 검증 |
| 10D-3B. Public Production Activation | Cloudflare, secret, 실제 User, schedule/replication | 허용된 두 사용자의 실제 운영 시작 |

## Slice 3 구현 경계

Transfer/Card는 Basic Ledger의 Account·Category 수동 설정과 INCOME/EXPENSE에 ASSET→ASSET 이체, CREDIT_CARD/LIABILITY 지출, ASSET→LIABILITY 카드대금 납부를 추가한다. 거래 수정은 지원 유형 사이에서 expected Entry set을 완전히 재구성한다.

LIABILITY source 이체, REFUND, 카드 명세·결제일·한도·할부, Category seed, Calendar/Statistics aggregation과 최종 Home 디자인은 Slice 3 완료 조건이 아니다.

## Slice 5 구현 경계

Budget은 Household timezone 월 단위로 HOUSEHOLD, 실제 Member별 PERSONAL, SHARED와 선택 EXPENSE Category의 예산을 저장한다. 사용액은 Transaction의 `NORMAL EXPENSE - REFUND EXPENSE`에서 매번 파생하며 미설정과 0원, 초과 상태를 구분한다.

Slice 5는 Budget CRUD, optimistic locking, 기본 Scope 카드, 사용자 설정 Category Budget, 월 이동과 기존 Transaction 목록을 재사용한 drill-down까지 포함한다. 자동 이월·전월 자동 복사, 거래 저장 차단, REFUND 생성, Statistics·Recurring·Goal·Assets 구현은 포함하지 않는다.

## Pre-Statistics Refund Correctness Gate

Slice 6에 들어가기 전에 ADR-004의 REFUND Transaction을 실제 write path로 활성화한다. 원 NORMAL EXPENSE 하위 resource에서 전체·부분 환불을 생성하고, 원 거래의 Scope/Owner/Payer/Category/PRIMARY Account와 Entry 방향을 상속한다.

원 거래 row lock 뒤 active refund 합계를 계산해 동시 요청에서도 누적 환불액이 원 금액을 초과하지 않게 한다. active Refund가 있는 원 거래의 금융 edit/delete는 차단하고 Refund는 logical delete 후 필요하면 재생성한다. Calendar, Budget, Account 잔액은 active Refund 생성·삭제를 같은 원장 의미로 즉시 반영한다.

이 Gate는 Slice 번호를 재정의하지 않으며 Statistics, Recurring, Goal, Assets, production 작업을 포함하지 않는다. 기존 V1~V6 schema가 계약을 지원하므로 migration을 추가하지 않는다.

## Slice 6 구현 경계

Statistics는 current Household의 유효 Transaction, Account Entry, Account 속성에서 기간·주체별 수입, 순소비, 저축, 저축률과 주체·Category·Account·월 breakdown을 매번 파생한다. current/comparison 범위는 Household timezone의 포함 날짜이며 비율은 소수점 한 자리 `HALF_UP`, 분모가 0이면 `null`이다.

수입·순소비·Category·Account·주체 drill-down은 기존 Transaction 목록을 재사용하고, 저축은 impact 0인 Transfer를 제외하는 전용 read endpoint를 사용한다. 저축은 Transfer에 Scope가 없으므로 ALL에서만 제공하며 개인·공동 view에 Account ownership으로 귀속하지 않는다.

Slice 6은 Statistics read model/API, 기간·주체 URL state, 월별 표와 drill-down을 포함한다. 통계 persistence/cache/materialized view/Redis, 근거 없는 index, Recurring·Goal·Assets·CSV·PWA·production 작업은 포함하지 않으며 schema migration을 추가하지 않는다.

## Slice 7 Recurring 구현 경계

Recurring은 Household timezone의 `start_date` anchor와 `scheduled_local_time`을 가진 rule을 저장하고 due occurrence마다 기존 canonical posting 로직으로 일반 Transaction과 Account Entry를 생성한다. rule 자체는 잔액·Calendar·Budget·Statistics에 포함하지 않는다.

V7은 rule/template Account table, generated lineage와 full occurrence unique, operational cursor를 additive로 추가한다. backend minute poll은 occurrence별 새 transaction에서 rule row lock과 due 재확인, generated 원장 저장, cursor advance를 원자 처리하고 bounded catch-up과 one-rule failure isolation을 제공한다.

Settings Sheet는 active/paused/ended 목록, 생성·수정·중지·재개를 제공한다. pause 기간은 resume 시 소급 생성하지 않고 generated history는 rule edit와 독립적인 snapshot으로 유지한다. recurring REFUND, `auto_post=false`, LIABILITY source, 예정 거래 승인, 알림, 별도 하단 tab, production 작업은 포함하지 않는다.

## Slice 8 Marriage Goal 구현 경계

Marriage Goal은 Household당 MARRIAGE 하나와 실제 Account link를 저장하되 잔액·월별 aggregate·기여금 ledger를 저장하지 않는다. 현재 보유금은 연결 Account의 canonical current balance 합이고 순저축은 current link와 `linked_at` 이후 Goal 안팎을 오간 TRANSFER에서 파생한다.

V8은 Goal/audit과 same-Household GoalAccount link, Household MARRIAGE partial unique, Account assignment unique를 additive로 추가한다. Account 연결은 기존 posting과 같은 Account row lock에서 snapshot을 잡고 target 수정은 optimistic version을 사용한다.

Home shell은 Goal 없음/연결 없음/실제 card 상태로 교체되고 card에서 `?screen=goal` 상세로 이동한다. 상세는 current/target/rate/remaining, 이번 달, 완료 3개월 평균과 projection 상태, 6개월 추세, Account, Transfer 근거를 제공한다. CUSTOM UI, GoalContribution, Goal 삭제, Assets, production asset/deploy는 포함하지 않는다.

## Slice 9 Assets 구현 경계

Assets는 current Household의 active·archived Account와 유효 Account Entry에서 현재 Account 잔액, 총자산, 총부채, 순자산을 매번 파생한다. PERSONAL 소계는 Account owner, SHARED 소계는 Account ownership을 기준으로 하며 Transaction Scope로 Account 소유를 추론하지 않는다.

월 추이는 Household timezone 기준 직전 11개 완료 월말과 현재 시점 한 점을 제공한다. Account의 `opening_balance_as_of` 이전 월 기여도는 0이고, 과거 거래 수정·논리삭제는 다음 조회부터 해당 월말을 다시 계산한다. 현재 점은 같은 repeatable-read snapshot의 현재 Household 합계와 정확히 일치한다.

Frontend는 기존 Assets 하단 destination을 활성화하고 actual Member/공동 소유 filter, accessible 추이 표, ASSET/LIABILITY Account 목록과 Settings Account 관리 진입을 제공한다. Goal link는 Assets 원장 값을 바꾸지 않는다. 별도 aggregate/cache/table, migration, Account write path 변경, Goal 지표 병합, CSV·PWA·production 작업은 포함하지 않는다.

## Slice 10 운영 Gate

Slice 10은 CSV, PWA, runtime harness, 실제 운영 활성화를 한 PR이나 한 승인으로 묶지 않는다.

- **10A CSV Export**: current Household의 유효 Transaction과 canonical Entry를 Household timezone 기간으로 읽어 한국어 CSV attachment를 생성한다. 별도 persistence, migration, background job, server temp file은 만들지 않는다.
- **10B PWA Installability**: 최종 한글 앱 이름·production icon 결정 전까지 보류한다. 결정 뒤 manifest와 service worker 설치 계약을 별도 검증한다.
- **10C-1 Immutable Runtime Harness**: digest-pinned multi-stage image, non-root same-origin Nginx, production Spring profile, image-only Compose를 합성 설정과 disposable PostgreSQL로 검증한다. Web만 loopback에 publish하고 API/DB host port, source mount, local identity를 금지한다.
- **10C-2A Backup/Restore Safety Gate**: existing healthy PostgreSQL의 one-shot custom dump를 atomic bundle, checksum, 비민감 metadata와 latest-success marker로 commit한다. 합성 non-empty DB를 별도 project/volume에 실제 복구하고 V1~V8, row count, financial sample, 제약과 production API readiness를 검증한다.
- **10C-2B1 Operational Status Harness**: exact Compose runtime, loopback Nginx health, process-local recurring scheduler raw signal, 10C-2A verified marker/inventory와 backup filesystem을 read-only canonical JSON으로 결합한다. unknown/unreachable/invalid를 success로 위장하지 않고 secret·PII·재무 상세·absolute path를 제외한다.
- **10C-2B2 Monitor/Alert Policy**: B1 raw snapshot에 service 2회, recurring startup/stale 5분과 rule failure 3 poll, local backup 7시간, disk 80/90% 정책을 적용한다. repository 밖 owner-only 최소 state, non-blocking lock, HomeOps reporter subprocess와 `DISK_LOW` ALERT/RECOVERED episode, monitor 60초와 backup `:35` LaunchAgent example을 synthetic하게 검증한다. service/origin/recurring/backup freshness는 local-only로 유지하고 실제 reporter/LaunchAgent, backup schedule·삭제·외부복제는 10D 전까지 활성화하지 않는다.
- **10D-1 Immutable Release/Deploy Source**: `main` exact HEAD에서 재사용 Full CI를 먼저 실행하고 명시적인 repository kill switch가 `true`일 때만 linux/arm64 API/Web/runtime-config exact-SHA artifact publish와 고정된 restricted SSH intent 전송 job이 실행되도록 source를 고정한다. runtime config change detector, secret-free scratch artifact와 local synthetic release gate까지만 포함한다.
- **10D-2A Candidate Migration/Validation Gate**: normal `production` startup은 Flyway를 비활성화하고 JPA validate만 수행한다. 동일 candidate API image의 profile-gated one-shot만 HTTP/bootstrap/scheduler 없이 Flyway와 JPA validate를 완료하고 명시적으로 종료한다. clean/idempotent/손상/연결·profile failure를 disposable PostgreSQL에서 검증하며 V1~V8 byte를 고정한다.
- **10D-2B1 Host State / Shared Operation Lock / Runtime-config Staging**: production worker의 app root를 `/Users/homeserver/Server/apps/our-ledger`로 고정하고 deploy와 standalone backup이 공유할 owner-only atomic directory lock을 source로 제공한다. runtime-config는 digest-derived `releases/<digesthex>`, relative atomic `current`, versioned `state/pending`만 허용하며 temp host와 synthetic backup에서 contention/corruption/crash를 검증한다. 실제 host path는 읽거나 쓰지 않는다.
- **10D-2B2 Host Deployment Transaction**: B1 lock/state authority 아래 restricted host wrapper, stdin-only registry token, exact artifact 검증, writer quiesce, verified backup, 10D-2A migration, same-SHA cutover, readiness, schema-aware rollback과 HomeOps lifecycle을 source로 조합하고 pure/synthetic gate로 검증한다.
- **10D-3A1 Production Household Bootstrap One-shot Gate**: 동일 candidate API image의 `production,bootstrap` profile이 Flyway/Web/recurring/local identity 없이 JPA validate 뒤 최대 8 KiB exact JSON stdin을 한 번 처리한다. empty DB는 exact 2 User/1 Household/OWNER·MEMBER를 생성하고 동일 입력은 state/ID 변화 없이 검증하며 partial/mismatch/extra 상태와 입력·profile·DB/schema 오류는 fail closed한다. actual production input/DB는 사용하지 않는다.
- **10D-3A2 Fresh-host Bootstrap Transaction Source**: repository 밖 owner-only one-time input, pre-current fixed ingress와 immutable runtime staging을 B1 lock 아래 `fresh PostgreSQL → migration → bootstrap → normal readiness → first verified backup → durable current/state`로 조합한다. 실제 값·host 실행은 여전히 제외한다.
- **10D-3B0 Exact-SHA GHCR Publish-only Source**: live `main` exact HEAD와 같은 repository의 성공한 Release Source Harness run에 결합된 같은 SHA만 입력받는다. API/Web/runtime-config를 ARM64 digest-first로 발행하고 세 exact tag의 absent/same/conflict preflight와 postflight를 수행하되 Tailscale/SSH/deploy/Production environment와 kill switch를 사용하지 않는다. source PR과 Hosted CI에서는 실제 GHCR workflow를 실행하지 않는다.
- **10D-3B3A Encrypted Offsite Backup Source**: committed `last-success.json`의 latest verified bundle 전체를 plaintext tar file 없이 `bsdtar stdout → age public recipient`로 암호화한다. owner-only local ciphertext staging, target `.partial` fsync/hash, final rename/reverify, atomic offsite marker와 8시간 read-only freshness를 고정하고 실제 `age` round-trip/failure matrix를 synthetic path에서 검증한다. 실제 recipient/config/iCloud directory/LaunchAgent는 만들거나 실행하지 않는다.
- **10D-3B3C Runtime-config Evolution Bridge**: production `9dd350b...` worker가 받는 manifest 없는 Legacy V1 20-file shape와 content hash를 동결한다. bridge artifact는 이 shape를 유지하되 worker는 strict `runtime-manifest.json` V2의 exact payload/mode/type을 분류·검증·stage할 수 있다. offsite source는 bridge artifact에서 제외하고 별도 V2 source Gate까지 활성화를 분리한다.
- **10D-3B3F Manifested Runtime V2 Source Gate**: root manifest mode `0600`과 sorted exact 22-file payload를 `scratch` linux/arm64 artifact로 활성화한다. detector·Dockerfile·manifest source를 동기화하고 actual build/export를 bridge worker로 preflight·추출·stage·re-read/hash 검증하되 GHCR publish, host update와 offsite 실행은 하지 않는다.
- **10D-3B3J12 Production Backup/Offsite Fixed Bootstrap Source Gate**: schedule activation이 요구하는 두 fixed ingress의 canonical source를 Manifested Runtime V2 payload에 추가한다. `/bin/bash`, system-only `PATH`, sanitized environment, exact `runtime-config/current` dispatch와 backup argc 0/offsite `run` only interface를 고정하며 source release·host update·fixed path install·LaunchAgent activation은 후속 Gate로 분리한다.
- **10D-3B Public Production Activation**: actual GHCR/Tailscale/SSH credential, Cloudflare/도메인/secret/User, backup schedule·retention·외부 암호화 복제와 public smoke를 각각 승인한 뒤 운영을 시작한다.

10D-2B2, 10D-3B0, 10D-3B3A, 10D-3B3C, 10D-3B3F와 10D-3B3J12 완료는 restricted transaction, publish-only, encrypted offsite source, runtime evolution bridge, Manifested V2 artifact와 fixed schedule bootstrap source가 local/Hosted synthetic gate에서 검증됐다는 뜻이다. 후속 Runtime V2 GHCR publish/host update, fixed host path install, forced-command, Tailscale/SSH credential과 LaunchAgent 등록이 없으므로 artifact publish, production status/backup/migration/reporter/offsite 실행, disaster recovery 준비 완료, schedule/Cloudflare/PWA/production activation 또는 deploy 완료를 의미하지 않는다.

## Release Gate

- `dev`는 검증된 Slice를 누적한다.
- `dev → main`은 의미 있는 사용자 흐름이 완료됐을 때만 진행한다.
- Production credential, 실제 DB migration, Cloudflare Access/Tunnel 설정, 배포는 별도 운영 Gate를 통과해야 한다.
- 재무 불변식 테스트가 실패하면 release할 수 없다.
- production에서 Access JWT 검증 우회 경로가 존재하면 release할 수 없다.

## 출시 전 결정 항목

다음은 현재 구현을 막지 않으므로 해당 Slice에서 확정한다.

- 앱 이름의 최종 한글 브랜드명
- 대표 아이콘, 색상, 상세 디자인 토큰
- 실제 결혼자금 목표 금액과 목표일
- 운영 백업 보관기간과 외부 백업 위치
- 실제 도메인과 Cloudflare route
- Cloudflare Access session duration
- 내부 User bootstrap/provision 운영 절차
