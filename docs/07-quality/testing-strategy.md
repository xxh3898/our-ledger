---
status: active
version: 1.8
last_updated: 2026-08-30
related:
  - ADR-008
  - 07-quality/financial-invariants.md
  - AGENTS.md
---

# 테스트 전략

## Foundation

- bootstrap class의 Spring Boot 구성 단위 테스트
- PostgreSQL 18.6 Testcontainers 기반 Spring context 기동
- clean database의 Flyway `V1__foundation.sql` 적용
- JPA `ddl-auto=validate` 계약
- `/actuator/health` HTTP `200`과 `UP` 응답
- React 기본 화면 component test
- ESLint, TypeScript typecheck, Vite production build

host에 Java/Node가 없는 local 환경은 Docker socket mount 없이 격리 external PostgreSQL과 build container를 사용한다. Hosted Backend CI는 기본 Testcontainers mode를 실행해 container 기반 연결 경로를 반드시 보완한다. 두 경로에서 같은 Flyway, JPA, health 관찰 결과를 검증한다.

## Backend

### 단위 테스트

- Transaction 생성 규칙
- Entry delta 계산
- 환불 가능액
- 저축액과 지표 공식
- 반복 날짜 계산
- Goal 예상일

### 통합 테스트

PostgreSQL Testcontainers를 사용한다.

- Flyway 전체 적용
- CHECK, unique, composite FK
- JPA mapping
- Household 격리
- 동시 수정 version 충돌
- 반복 생성 idempotency

Transfer/Card Ledger Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1→V5 clean 적용과 JPA `ddl-auto=validate`
- Account PERSONAL/SHARED CHECK, Member composite FK, KRW/last-four/savings, CREDIT_CARD/LIABILITY 제약
- Category Group/type composite FK와 active case-insensitive name unique
- Transaction positive amount/scope/category CHECK, Member/Category/audit composite FK
- Entry의 Transaction/Account composite FK, nonzero delta, duplicate PRIMARY unique
- INCOME `+100000`, ASSET EXPENSE `-12000`, 카드 EXPENSE `+amount`
- ASSET→ASSET SOURCE `-amount`/DESTINATION `+amount`, ASSET→LIABILITY 양쪽 `-amount`
- update 후 PRIMARY 또는 SOURCE/DESTINATION exact set으로 교체되고 stale role/delta가 남지 않음
- logical delete 후 목록/detail/잔액 제외, stale version `409`
- same/archived/unsupported/foreign transfer, invalid stored Entry set 거부와 atomic rollback
- Entry가 연결된 Account의 posting 분류 변경 거부와 기존 거래 조회·잔액 보존

Calendar Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- 현재월과 이전월 `NORMAL EXPENSE - REFUND EXPENSE` 합계와 차이
- INCOME/TRANSFER 순소비 제외, 논리삭제 거래 전체 제외
- ALL, 두 실제 Member의 PERSONAL, SHARED 분리
- PERSONAL owner 누락과 잘못된 scope/owner 조합 `400`
- 다른 Household Member를 PERSONAL owner로 요청할 때 `404`
- `Asia/Seoul` 자정 UTC 경계의 월·날짜 귀속
- 날짜별 순소비 합과 월 순소비의 같은 정의
- TRANSFER의 ALL 거래 수 포함과 PERSONAL/SHARED 제외

Budget Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1→V6 clean 적용과 JPA `ddl-auto=validate`
- `budget_month` 월 1일, amount 0 이상, scope-owner CHECK
- `UNIQUE NULLS NOT DISTINCT`의 null owner/category 포함 identity 중복 차단
- Member/Category composite FK와 service의 current Household 404
- active EXPENSE Category만 신규 연결하고 archived Category 기존 row는 표시
- HOUSEHOLD, 실제 Member별 PERSONAL, SHARED, Category 순소비 분리
- INCOME/TRANSFER/논리삭제 제외, REFUND 차감, Household timezone 월 경계
- 신용카드 구매 EXPENSE 포함과 카드대금 TRANSFER 제외
- Budget 미설정과 0원, 초과 후 Transaction 저장 허용
- duplicate pre-check와 DB unique race의 `BUDGET_DUPLICATE`
- stale PATCH/DELETE의 `BUDGET_VERSION_CONFLICT`
- Budget CRUD의 인증·CSRF·IDOR와 REST Docs canonical request/response

Pre-Statistics Refund Correctness Gate는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- ASSET EXPENSE Refund의 positive PRIMARY와 CREDIT_CARD/LIABILITY Refund의 negative PRIMARY
- 전체·여러 부분 환불의 active 합계와 original remaining
- original `PESSIMISTIC_WRITE` lock을 경합하는 동시 요청에서 한 요청만 성공해 누적 상한을 보존
- current Household, NORMAL EXPENSE, active row, valid PRIMARY exact set fail-closed
- archived Account/Category original의 실제 reversal 허용과 Scope/Owner/Payer/Category/Account 상속
- active Refund가 있는 original 금융 edit/delete 차단과 occurredAt/memo-only update 허용
- Refund generic PATCH 거부, version 기반 logical delete, delete 뒤 cap·Account·Calendar·Budget 복원
- dedicated Refund endpoint의 인증·CSRF·IDOR와 REST Docs canonical request/summary/error/delete

Statistics Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- NORMAL INCOME, NORMAL EXPENSE - REFUND EXPENSE와 논리삭제 제외
- 카드 구매 포함, 카드대금 TRANSFER 제외, PRIMARY Account breakdown 검산
- ALL/각 PERSONAL Member/SHARED Scope, foreign Member 404, invalid owner 조합 400
- Household timezone 포함 날짜와 custom partial month, 빈 calendar month 0 row
- current/comparison 독립 계산, previous 0 percent null, income 0 savings rate null
- subject 합과 Account 합이 summary 순소비와 정확히 일치
- Refund가 같은 Category/PRIMARY Account에서 차감되고 archived reference가 유지됨
- 비저축→저축, 저축→비저축, 저축→저축, 비저축→비저축 Transfer matrix
- savings Account EXPENSE가 저축 인출로 계산되지 않음
- PERSONAL/SHARED savings amount/rate unavailable
- savings activity impact 합과 ALL summary savings amount 일치
- 인증, validation, canonical Statistics/savings activity REST Docs

Recurring Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- Flyway V1→V7 clean 적용과 JPA `ddl-auto=validate`
- rule schedule CHECK, role별 Account template 제약, Household composite FK
- 생성 Transaction provenance의 둘 다 null 또는 둘 다 non-null CHECK와 논리삭제를 포함하는 full unique
- DAILY/WEEKLY/MONTHLY/YEARLY interval, 최초 anchor, 짧은 달과 윤년 clamp
- Household timezone local time의 due 경계와 지연 실행 catch-up batch 상한
- INCOME, ASSET EXPENSE, 카드 EXPENSE, TRANSFER의 canonical Entry·잔액·Calendar·Budget·Statistics 반영
- rule row lock을 경합하는 PostgreSQL worker의 발생일 중복 방지와 cursor 원자성
- 생성 Transaction 논리삭제 뒤 같은 발생일 재생성 차단
- template 수정의 향후 snapshot 적용과 기존 생성 거래 불변
- 일시정지·재개의 소급 미생성, 종료일, active/paused/ended 상태
- 한 규칙의 invalid template 실패가 다른 due 규칙을 막지 않는 격리
- active reference lifecycle 차단, stale version, validation, Household IDOR, 인증·CSRF
- canonical Recurring create/list/update/conflict REST Docs

Marriage Goal Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- Flyway V1→V8 clean 적용과 JPA `ddl-auto=validate`
- Goal name/type/positive target/version CHECK, Household MARRIAGE partial unique, future CUSTOM 비제한
- Goal/Account/Member audit composite FK와 Account 전체 assignment unique
- same Household 동시 MARRIAGE create 중 정확히 하나만 성공하고 stable `GOAL_ALREADY_EXISTS`
- eligible active savings ASSET 연결, archived/savings-disabled/LIABILITY 거부, foreign Account 404
- 동일 Account 동시 link 중 정확히 하나만 성공하고 stable `GOAL_ACCOUNT_ALREADY_ASSIGNED`
- Goal link가 Account lock을 가진 동안 동시 posting이 실제로 대기하고 `starting_balance`가 pre/post 중 하나의 완전한 값임
- current amount가 opening + active Entry delta 합이고 starting snapshot을 중복 가산하지 않음
- logical delete, Refund balance 효과, linked archived Account 유지, unlink 즉시 제외와 원장 불변
- Goal 경계 Transfer 네 방향, 다른 savings Account 유입, linked_at 이전, INCOME/EXPENSE/REFUND 비분류
- Household timezone 현재 월, 빈 달 포함 6개월 추세, 완료 3개월 정수 평균
- ACHIEVED/INSUFFICIENT_HISTORY/NON_POSITIVE_AVERAGE/PROJECTED와 ceil 예상 월
- impact 0 제외 최근 활동, 안정 정렬, recurring provenance
- 같은 version target 동시 PATCH 한 건만 성공, stale error, 인증·CSRF·Household 경계
- canonical Goal empty/read/create/update/link/unlink/error REST Docs

Assets Slice는 추가로 다음을 실제 PostgreSQL에서 검증한다.

- active·archived Account, opening balance와 active Entry delta의 current balance
- ASSET/LIABILITY signed 합, 음수·0 balance, Household/actual Member/SHARED 검산
- Account ownership 귀속과 Transaction Scope의 독립성, foreign Household data 제외
- INCOME/EXPENSE/REFUND/TRANSFER, generated recurring Transaction, logical delete의 원장 효과
- Goal Account link/unlink와 snapshot의 Assets 값 불변
- Household timezone 직전 11개 완료 월말과 현재 한 점, UTC 자정 경계, opening date 이전 0
- current trend 점과 current summary의 같은 snapshot 일치, Account 없음 12개 zero point
- current balance·baseline·월 delta의 bounded batch query 구조와 N+1 부재
- canonical Assets response, `lastFour` 비노출, 인증 REST Docs

Immutable Production Runtime Harness Slice는 추가로 다음을 실제 Docker runtime에서 검증한다.

- Java 25 JDK→Distroless Temurin Java 25와 Node 24→Nginx multi-stage clean build, tag+manifest digest 고정
- Dockerfile-specific context allowlist와 최종 API image의 shell/package manager/build tool/source/test/cache, Web image의 Node/npm/source/node_modules 부재
- API/Web non-root, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, tmpfs, pid/resource limit
- PostgreSQL official entrypoint 호환 named volume, internal database network, API/DB host publish 부재
- Web 유일 port의 `127.0.0.1` ephemeral bind와 source/Docker socket/host network/privileged 부재
- Nginx root, hashed asset, SPA deep link와 `no-store`/immutable cache header
- `/api`와 `/api/**`의 canonical JSON 401, forged local identity 401, API body/status/content type passthrough
- Cloudflare JWT/Host/X-Forwarded-For/X-Forwarded-Proto/request ID proxy directive와 CSV `Content-Disposition` 비은닉
- public `/actuator/**` 404, safe static `/healthz`, internal API readiness
- normal production profile의 env datasource, Cloudflare required 설정, Flyway false, JPA validate, bootstrap false와 recurring scheduler true
- 같은 candidate image의 profile-gated one-shot에서만 Flyway true, Web NONE, bootstrap/scheduler false와 명시적 exit 0
- unmigrated DB normal startup의 schema mutation 없는 failure, one-shot V1→V8 clean history와 migrated normal API restart 뒤 history/readiness 유지
- migration idempotent rerun의 fixture/cursor 불변, failed Flyway history, synthetic schema damage, unreachable DB, invalid profile/flag의 nonzero와 credential/PII 비노출
- V1~V8 migration regular file의 filename과 byte SHA-256 고정
- Spring graceful shutdown log/exit와 성공·실패 trap 이후 project container/network/volume/image tag residue 0

`scripts/verify-production-runtime.sh`는 실제 운영 값 대신 고유 Compose project, Docker가 할당한 loopback port, 합성 credential과 disposable volume만 사용한다. `api-migration`과 normal `api`는 같은 exact-HEAD image를 사용하며 같은 script를 local `verify.sh`와 Hosted Full CI exact HEAD에서 실행한다. 실제 production deployment, migration, backup/restore, Cloudflare/Tunnel과 monitor는 이 테스트 대상이 아니다.

Backup/Restore Safety Gate는 추가로 실제 PostgreSQL 18.6 container에서 다음을 검증한다.

- env/backup path의 absolute/canonical/owner-only/repository 밖 경계와 root·Docker data·symlink·traversal 거부
- exact Compose project/config/image label, running/healthy PostgreSQL과 project-scoped volume/internal network
- restrictive umask, shared project operation lock contention, user-controlled text 없는 strict artifact filename
- custom-format online `pg_dump`, nonzero/`PGDMP`/`pg_restore --list`, SHA-256/size/metadata/checksum 일치
- partial owner-only bundle의 atomic directory rename과 verified success 뒤 `last-success.json` atomic update
- collision, shared lock, path, missing project/service, stopped/unhealthy DB, injected pg_dump failure에서 이전 bundle/marker 보존
- zero/truncated/corrupt archive, checksum mismatch, metadata mismatch와 archive-list failure의 restore 전 거부
- 2 User/1 Household/2 Member, 세 Account nature/type, Category, INCOME/EXPENSE/TRANSFER/REFUND와 Budget/Recurring/Goal synthetic fixture
- source와 별도 고유 project/network/volume의 empty PostgreSQL에 fail-fast single-transaction restore
- Flyway V1→V8, core row, Transaction/Entry/Refund lineage, Account balance와 net worth source/target equality
- Household composite FK/Entry·Goal Account unique enforcement, restored V8의 same-image migration rerun과 normal production API JPA/readiness startup 뒤 state 불변
- missing restore DB failure와 성공·실패 trap 뒤 exact project container/network/volume/image tag residue 0

`scripts/verify-backup-restore.sh`는 source/target/failure PostgreSQL에 host port를 publish하지 않고 합성 credential과 검증 중 생성한 exact-HEAD API image만 사용한다. dump는 임시 owner-only directory에만 두고 log 또는 GitHub Actions artifact로 업로드하지 않는다. 실제 production backup/restore, schedule, retention, 외부복제는 테스트 대상이 아니다.

Operational Status Harness는 추가로 다음을 검증한다.

- process-local recurring state의 초기/disabled, poll start/completion, success/advanced count, top-level failure/rethrow, consecutive reset과 concurrent snapshot
- 여러 rule failure의 total/current poll count, 비식별 field exact contract와 기존 one-rule failure isolation
- `recurringScheduler` HealthIndicator의 `UNKNOWN/UP/DOWN`, operations group detail, global detail 비노출과 readiness/liveness 독립
- 기존 `HttpHealthCheck`의 one-argument/HTTP 200 계약과 `HttpFetch`의 HTTP status/body, non-200, network failure 구분
- backup directory read-only validation이 write probe를 만들지 않고 backup 생성 validator는 기존 probe/fsync를 유지함
- exact Compose label/config authority, running/stopped/unhealthy/missing service, loopback origin, API unreachable과 canonical JSON exact field
- valid/missing/invalid/future marker, valid/invalid/incomplete/foreign inventory, freshness와 filesystem available/unavailable
- container environment, raw health body, secret/email/재무 상세/artifact 이름/absolute path가 snapshot에 없는 privacy allowlist
- status command가 `config --quiet`, `ps`, `inspect`, GET-only container exec 밖의 backup/DB/service/file mutation을 호출하지 않음

`scripts/verify-observability.sh`는 exact-HEAD API/Web image, 고유 Compose project와 owner-only 합성 backup/DB fixture를 사용한다. 같은 candidate image의 migration one-shot을 먼저 완료한 뒤 normal API에서 poll success, generated occurrence, isolated rule failure, API unavailable, process 재시작 뒤 not-yet-run reset과 public actuator 404를 검증한다. 성공·실패 뒤 container/network/volume/image/temp residue 0과 backup byte-identical을 요구한다. local `verify.sh`와 Hosted Full CI의 독립 `observability` job에서 실행하며 실제 production status/monitor/alert는 대상이 아니다.

Monitor/Alert Policy Harness는 추가로 다음을 검증한다.

- healthy snapshot, service/origin/recurring reachability 1회/2회와 target별 독립 recovery
- recurring startup 5분 exact boundary, completed poll stale `>5m`, top-level failure 즉시 CRITICAL
- 같은 recurring poll 재평가 idempotency, failed poll 1/2/3과 새 clean poll reset
- backup 7시간 exact boundary, marker failure, invalid/incomplete/foreign inventory 의미
- filesystem 80/90 exact boundary와 unavailable
- result/signal/state exact allowlist와 raw snapshot/secret/PII/financial/path 비노출
- external state/backup/reporter canonical path와 mode, pairwise disjoint, atomic state replace, corruption preservation, non-blocking lock
- synthetic `report-homeops-event.py signal`의 exact JSON stdin, `shell=False`, bounded timeout/output, nonzero failure와 secret/origin argument·environment 부재
- `DISK_LOW` ALERT/RECOVERED episode, durable pending save/clear, same-key retry와 unsupported local signal non-delivery
- recent4+daily7 KST retention matrix와 symlink/invalid/future/incomplete/foreign fail-safe, tree byte-identical
- monitor 60초, backup `:35` 네 시각, fixed external bootstrap, `KeepAlive` 부재의 plist parse/lint

`scripts/verify-monitor-policy.sh`는 Python pure/unit, synthetic external reporter와 plist parser만 사용하고 Docker, actual status/backup/HomeOps reporter·spool·API/LaunchAgent를 사용하지 않는다. local `verify.sh`와 Hosted Full CI의 독립 `monitor-policy` job에서 실행한다.

Immutable Release/Deploy Source Harness는 다음을 추가로 검증한다.

- release helper의 exact 40자리 SHA, `sha256:` digest, bounded actor와 keep/update restricted command grammar
- command injection, extra argument, arbitrary path/image/shell fragment와 invalid/zero revision 거부
- runtime-config detector의 application-only `keep`, runtime source/force/bootstrap `update`, missing/non-ancestor range fail-closed
- `main` validation의 재사용 Full CI 단일 authority, production concurrency와 default-off kill switch
- publish/deploy job의 최소 permission, exact-SHA linux/arm64 image/OCI label/digest와 `latest` 부재
- publish/deploy privileged job의 third-party action exact 40-hex pin과 mutable tag 부재
- GHCR token stdin-only restricted SSH boundary와 token/secret의 command argument·artifact 비포함
- `scratch` runtime-config artifact의 source별 single COPY, exact regular-file allowlist와 `0600`/`0700` mode, expected directory hierarchy, symlink와 env/key/dump/state 부재. BuildKit parent directory mode는 고정하지 않고 10D-2B1 state source/10D-2B2 host install authority와 분리한다.
- 고유 label을 가진 disposable image/container의 성공·실패 cleanup과 residue 0

`scripts/verify-release-transport.sh`는 helper unit test 뒤 local Docker `--platform linux/arm64 --network none`으로 runtime-config source만 build/extract한다. 합성 `.env.production.example`로 Compose render와 공개 script help를 확인하고 actual registry login/push, Tailscale, SSH, GitHub deployment, Mac mini 또는 `/Users/homeserver/Server`를 사용하지 않는다. local `verify.sh`와 Hosted Full CI의 독립 `release-transport` job에서 실행한다.

Host State / Shared Operation Lock Harness는 다음을 추가로 검증한다.

- fixed production root source와 production CLI의 root/state/Compose override·environment bypass 부재
- owner-only host layout, atomic directory operation lock의 first/second holder, stale/symlink/tampered lock fail-closed
- public standalone backup과 synthetic deploy의 공통 lock contention, lock-held internal backup core direct invocation의 self-deadlock 부재
- exact digest-derived release path, exact allowlist/mode, same-content reuse와 same-digest different-content overwrite 거부
- source/release symlink, hardlink, FIFO, unexpected entry, path-like digest와 external current target 거부
- relative current atomic pointer와 formatVersion 1 state/pending의 `0600`, exact schema, file/directory fsync와 temp residue 부재
- pending 중 신규 stage/transaction 차단, crash 뒤 pending 보존, unchanged previous에서만 explicit abandoned pending/stage cleanup 허용
- runtime-config Dockerfile, detector, release gate의 new host/core source와 non-executable internal core mode 동기화

`scripts/verify-host-state.sh`는 Python unit과 shell/source contract만 temp root에서 실행하고 실제 `/Users/homeserver/Server`, production resource와 network를 사용하지 않는다. `scripts/verify-backup-restore.sh`는 같은 test-only injected host adapter 아래 actual internal backup core를 disposable PostgreSQL과 경합시켜 artifact 의미가 유지됨을 검증한다. local `verify.sh`와 Hosted Full CI의 독립 `host-state` job에서 실행한다.

CSV Export Slice는 추가로 다음을 실제 PostgreSQL과 byte-level assertion으로 검증한다.

- 필수/parse/역전 날짜와 3,653일 허용·3,654일 거부 stable code
- Household timezone `[fromStart, toPlusOneStart)` 양 끝과 `occurred_at ASC, id ASC`
- INCOME, ASSET/CREDIT_CARD EXPENSE, ASSET→ASSET/LIABILITY TRANSFER, partial/full REFUND
- generated recurring provenance, archived Account/Category, PERSONAL/SHARED owner/payer
- logical delete와 foreign Household 제외, canonical Entry 손상 409
- UTF-8 BOM, 19개 고정 header, CRLF, comma/quote/newline, nullable cell
- `=`, `+`, `-`, `@`, TAB, CR formula prefix와 trim 전·후 방어
- `Content-Type`, attachment filename, `no-store`, `nosniff`, 401/403와 REST Docs
- Transaction/Entry/Account/Category/Member 최대 5개 query와 temp file/persistence 부재
- `lastFour`, email, foreign reference, credential 비노출

Auth/Household Slice는 추가로 다음을 PostgreSQL에서 검증한다.

- Flyway V1/V2 clean 적용과 JPA schema validate
- email normalization과 case-insensitive duplicate 차단
- Household `KRW`/`Asia/Seoul` 기본값
- duplicate membership과 second OWNER DB 차단
- locked service transaction의 third Member 차단
- bootstrap exact rerun no-op과 partial/conflicting state fail-fast

### 인증·인가 테스트

production 인증 계약은 Cloudflare Access이므로 다음을 자동 검증한다.

- 유효한 Access JWT가 내부 활성 User에 매핑됨
- 잘못된 서명 거부
- 잘못된 issuer(`iss`) 거부
- 잘못된 audience(`aud`) 거부
- 만료 token 거부
- future `nbf` token과 missing email claim 거부
- 내부 User 미존재/비활성 상태 거부
- Household membership 없음 또는 ambiguous 상태 거부
- 다른 Household 리소스 접근 거부
- 일반 이메일 헤더만으로 인증할 수 없음
- production profile에서 개발용 identity adapter가 비활성
- state-changing 요청의 CSRF 또는 동등한 Origin 보호

Cloudflare 외부 서비스에 의존하지 않도록 테스트용 signing key/JWK와 test principal을 사용하되 production credential은 사용하지 않는다.

production 통합 테스트는 process-local HTTP JWK endpoint와 매 실행 생성한 RSA private key로 실제 RS256 token을 서명한다. repository에는 private key 파일이나 token fixture를 저장하지 않는다. production filter chain에 local identity filter가 없는지도 filter 목록과 HTTP 요청으로 확인한다.

### API 테스트

- 인증·인가·CSRF/Origin 보호
- validation과 error code
- filter 조합
- 삭제 후 계산 제외

`AuthHouseholdDocsTest`는 `/api/v1/me`, `/api/v1/households/current`, 401/403 error code, 임의 Household ID 비권한성, `XSRF-TOKEN`/`X-XSRF-TOKEN` 계약을 검증한다. test-only POST fixture는 token 없는 unsafe 요청을 403으로 거부하고 GET에서 받은 cookie token을 header로 보낸 요청만 허용한다.

## Frontend

- `/api/v1/me` loading과 정상 User/Household/role 렌더링
- 401 Cloudflare Access 인증 필요 상태
- 403 내부 User 미등록 상태
- 금액·날짜·필터 변환 단위 테스트
- 빠른 입력 form 컴포넌트 테스트
- 달력·예산·자산 상태 테스트
- 인증되지 않은 상태와 Access 재인증 이동 처리
- 핵심 사용자 흐름 E2E
- 모바일 viewport 접근성

`calendarState.test.ts`는 Household timezone 기본값, 잘못된 URL 정규화, 실제 Member ID, ALL/PERSONAL/SHARED API mapping, 월 이동 date clamp, Sunday-first grid를 검증한다.

`App.test.tsx`는 identity loading/401/403을 보존하며 다음 Calendar/Quick Entry 계약을 mock HTTP 경계에서 검증한다.

- Couple-first section 순서와 실제 Member 이름
- ALL/각 Member/SHARED의 월 요약·선택일 동일 적용
- transfer-only 무지출과 future Paw 제외
- 날짜 선택 URL/API, popstate 동기화
- 선택 날짜 전달과 current user PERSONAL 기본값
- numeric autofocus, ESC close, opener focus 복귀
- 중복 submit 방지, 500ms 성공 feedback, 같은 context 갱신
- 실패 시 Sheet·입력 보존
- 선택일 edit/delete 후 월·일 갱신
- 설정 Sheet의 Account/Category 기능 보존
- 활성 하단 destination과 `aria-current` 전환

같은 test는 Refund Correctness Gate에서 다음 계약을 추가로 검증한다.

- NORMAL EXPENSE만 Refund action 제공하고 REFUND/INCOME/TRANSFER는 제외
- partial/full summary, amount/date/memo-only Sheet, Household timezone 오늘
- client/server cap error 입력 보존과 pending 중복 submit 방지
- 성공 뒤 Calendar aggregate·해당 날짜 목록 갱신
- REFUND text/sign, generic edit 제외, 원 지출 보존 삭제 확인
- Sheet autofocus, Escape/backdrop/close와 opener 또는 context fallback focus

같은 test는 Budget Slice에서 다음 계약을 추가로 검증한다.

- Budget destination active state와 Calendar/Statistics/Assets 이동 회귀
- HOUSEHOLD/실제 Member/SHARED 기본 카드와 Category Budget
- 미설정, 0원, 100% 초과의 text·금액 구분
- `screen=budget&month=YYYY-MM` 월 이동과 popstate
- 생성 성공 refresh, duplicate 실패 입력 보존, 수정 stale 오류, 2단계 삭제
- active EXPENSE Category picker와 archived Category 표시
- month/scope/owner/category `type=EXPENSE` drill-down과 REFUND 표시
- Budget Paw FAB의 Household timezone 오늘 날짜

같은 test와 `statisticsState.test.ts`는 Statistics Slice에서 다음 계약을 추가로 검증한다.

- Statistics destination 활성/`aria-current`와 Calendar/Budget/Assets 이동 회귀
- 이번 달 ALL 기본값, 모든 preset의 이전 calendar range, custom same-day-count comparison
- invalid date/range/foreign Member canonicalization과 direct/back/forward URL state
- Member/SHARED API query mapping과 pending 중 stale 숫자 제거
- summary/comparison/month/Category/subject/Account의 amount와 계산 불가 text
- PERSONAL/SHARED 저축 unavailable 설명
- Transaction drill-down의 기간/Scope/type/Category/Account query와 REFUND `+금액`
- savings activity endpoint, Sheet focus/Escape/backdrop/opener 복귀
- Statistics Paw FAB의 Household timezone 오늘 날짜

같은 `App.test.tsx`는 Recurring Slice에서 다음 계약을 추가로 검증한다.

- 설정 Sheet의 active/paused/ended 목록과 schedule·Account·subject 표시
- 생성·수정 nested Sheet의 유형별 template, frequency/interval/date/time 입력
- pause/resume action과 소급 미생성 안내
- pending 중복 submit 방지, 실패 시 입력 보존, 성공 시 목록 refresh
- autofocus, Escape/backdrop close와 opener focus 복귀
- Calendar, Budget, Statistics, savings activity의 `반복` text badge

같은 `App.test.tsx`는 Marriage Goal Slice에서 다음 계약을 추가로 검증한다.

- Home의 Goal 없음 CTA 또는 actual current/target/rate/이번 달 card와 hardcoded shell 제거
- `?screen=goal` direct/refresh/back/forward와 새 Bottom tab 부재
- 상세 current/target/rate/remaining, projection 이유, 6개월 accessible SVG/table, linked Account/activity
- 생성 목표 금액 blank, 수정 version payload, pending 중복 submit 방지, stable error 뒤 입력 보존
- eligible Account 명시 선택, conflict 뒤 선택 보존, 연결/해제 확인과 read refresh
- archived linked Account와 `반복` provenance text, 수동 기여금 action 부재
- Sheet initial focus, Escape/backdrop/close, opener focus 복귀
- loading 중 이전 Goal 금융 수치 제거와 Goal 없음/연결 없음/error 분리

같은 `App.test.tsx`와 `assetsState.test.ts`는 Assets Slice에서 다음 계약을 추가로 검증한다.

- direct/refresh/popstate에서 all/actual Member/shared canonical URL과 invalid Member fail-closed
- actual API 총자산·총부채·순자산, 음수·0·archived/savings Account와 ASSET/LIABILITY 그룹
- 소유 filter가 현재 소계·Account만 바꾸고 Household 12-point 추이는 유지
- accessible SVG 이름과 12-row semantic table, current `진행 중` 의미
- loading 중 이전 금융 숫자 제거, stable error retry, 전체 Account 없음과 선택 bucket 없음 구분
- Account Settings opener focus 복귀와 Assets Paw Household 오늘, 전체 하단 destination 이동 회귀

같은 `App.test.tsx`는 CSV Export Slice에서 다음 계약을 추가로 검증한다.

- Settings `데이터 내보내기` section과 Household timezone 월 1일~오늘 기본값
- 날짜 수정, pending 중복 요청 차단, 실패 뒤 입력 보존
- same-origin CSV response의 Blob download, 안전한 server filename과 고정 fallback
- object URL revoke, 성공 status, Settings 유지와 opener focus 회귀
- `INVALID_REQUEST`, `EXPORT_RANGE_TOO_LARGE`, network, non-CSV response의 stable 오류
- local/session storage에 인증 token/cookie를 저장하지 않는 요청 경계

`budgetState.test.ts`는 timezone 현재 월, 잘못된 month 정규화, 연도 경계 월 이동과 Budget URL serialization을 검증한다.

## Production 보안 검증

배포 Gate에서는 자동 테스트 외에 다음을 확인한다.

- Access Allow 정책이 두 사용자 이메일만 허용
- `cloudflared` Access 검증 활성
- origin/API/DB 공용 포트 비노출
- Access를 우회하는 public hostname 부재
- 인증 token/cookie가 애플리케이션 로그에 남지 않음

실제 Cloudflare 설정 변경은 에이전트가 수행하지 않는다.

## 계약 테스트

Spring REST Docs를 사용해 API 구현과 문서를 동기화한다. `/actuator/health`와 internal `actuator-operations-health` 외에 Auth/Household Slice는 `current-user`, `current-household` response field snippet을 생성한다. 사람이 작성한 도메인 문서를 API 스키마로 대체하지 않는다.

Basic Ledger는 `LedgerApiDocsTest`의 실제 current Household/CSRF request로 `ledger-account-*`, `ledger-category-*`, `ledger-transaction-*` create/list/detail/update/delete, `ledger-refund-*`, `ledger-calendar-month` snippet을 생성한다. Budget은 `BudgetApiDocsTest`에서 `budget-create`, `budget-month`, `budget-update`, `budget-delete`, duplicate/version conflict snippet을 생성한다. Recurring은 `RecurringApiDocsTest`에서 `recurring-create`, `recurring-list`, `recurring-update`, `recurring-version-conflict` snippet을 생성한다. Marriage Goal은 `MarriageGoalApiDocsTest`에서 empty/read/create/update/link/unlink와 business error snippet을 생성한다. Statistics는 `StatisticsApiDocsTest`에서 `statistics-read-model`, `statistics-savings-activities`, `statistics-invalid-request` snippet을 생성한다. Assets는 `AssetsApiDocsTest`에서 `assets-read-model`, `assets-authentication-required` snippet을 생성한다. CSV는 `TransactionCsvExportApiDocsTest`에서 `transaction-csv-export`, `transaction-csv-export-range-too-large` snippet을 만들고 `TransactionCsvExportIntegrationTest`가 canonical byte를 고정한다.

## 회귀 우선순위

1. 재무 불변식
2. Household 경계
3. migration
4. 인증·인가
5. 핵심 입력·조회 흐름
6. 표현·디자인

## CI

`./scripts/verify.sh`가 단일 local 진입점이다. Pull Request required check에서 backend, frontend, docs, repository hygiene와 Release/Deploy source, host-state/shared operation lock, disposable production runtime, backup/restore, observability, monitor-policy/HomeOps smoke를 검증한다. `main` release workflow도 같은 reusable Full CI를 validation authority로 호출한다.
