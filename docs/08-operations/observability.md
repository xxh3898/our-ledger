---
status: active
version: 0.6
last_updated: 2026-08-29
related:
  - 06-security/privacy-model.md
  - 08-operations/backup-restore.md
  - 08-operations/deployment.md
  - ADR-005
  - ADR-008
---

# 관측성

## 현재 상태

Slice 10C-2B1은 existing production-like runtime과 10C-2A verified backup marker를 변경하지 않고 읽는 operational status harness를 구현했다. `production-status.sh`가 Web/API/PostgreSQL, loopback Nginx, process-local recurring scheduler, backup freshness/inventory와 backup filesystem을 canonical JSON object 하나로 결합한다. Slice 10C-2B2는 이 raw snapshot을 변경하지 않고 `monitor_policy.py` pure evaluator, owner-only 최소 state와 Uptime Kuma push worker를 별도 계층으로 추가한다.

실제 Mac mini production에서 status/monitor command를 실행하거나 LaunchAgent, Uptime Kuma monitor/email을 활성화하지 않았다. B2는 확정 policy와 synthetic local/Hosted gate, 설치하지 않는 plist example까지만 제공한다. external state/config/bootstrap 생성과 실제 activation은 10D의 별도 운영 승인 대상이다.

## Recurring process-local signal

`RecurringSchedulerOperationalState`는 다음 non-sensitive field만 process memory에 보관한다.

- `enabled`, `processStartedAt`, `pollCountSinceStart`
- `lastPollStartedAt`, `lastPollCompletedAt`, `lastPollSucceeded`
- `lastAdvancedOccurrenceCount`, `lastPollRuleFailureCount`
- `totalRuleFailureCountSinceStart`, `consecutivePollExecutionFailures`
- `lastPollExecutionFailureAt`, `lastRuleFailureAt`

poll 시작을 기록한 뒤 generation이 정상 반환하면 advanced count와 success를 기록한다. top-level `RuntimeException`은 failure를 기록하고 같은 예외를 재전파한다. 다음 성공 poll은 consecutive execution failure count를 0으로 reset하되 마지막 failure timestamp는 원인 조사용 raw history로 유지한다.

rule 단위 `RuntimeException`은 기존 warn log와 one-rule isolation을 유지하면서 current/total count와 timestamp만 기록한다. recurring ID, Household/User/Member, email, memo, amount, Category/Account와 exception message/stack은 state와 health detail에 저장하지 않는다. process restart 시 전체 state가 reset되고 첫 poll 전에는 성공으로 간주하지 않는다.

## Internal operations health

Spring Boot health component 이름은 `recurringScheduler`, custom group은 `/actuator/health/operations`다.

- poll 미실행 또는 진행 중: `UNKNOWN`
- 마지막 top-level poll 정상 완료: `UP`
- 마지막 top-level poll 예외 종료: `DOWN`
- rule 단위 failure가 있어도 top-level poll이 정상 완료하면 `UP`이고 count로만 표현

`operations` group에는 이 component만 include하고 group에서만 `show-components: always`, `show-details: always`를 사용한다. global `show-details: never`는 유지하고 recurring component를 liveness/readiness에 추가하지 않는다. 따라서 recurring generation failure는 API container restart/recreate 신호가 아니다.

API는 host port가 없고 public Nginx는 `/actuator`와 `/actuator/**`를 404 처리한다. `/healthz`는 `ok`만 반환하는 Nginx 자체 상태다. status collector는 API container namespace에서 compiled GET-only `HttpFetch`로 operations response를 읽으며 raw body를 출력하지 않는다.

## Read-only status command

```bash
./scripts/production-status.sh \
  --project-name <exact-production-compose-project> \
  --env-file <absolute-owner-only-file-outside-repository> \
  --backup-dir <absolute-dedicated-owner-only-directory>
```

project name은 strict pattern을 따르고 env file은 owner-only `0600`, backup directory는 owner-only `0700`이며 둘 다 repository 밖 canonical path여야 한다. exact repository `compose.prod.yaml`과 existing container의 project/service/config-file label이 일치해야 한다. 다른 stack 또는 중복 authority가 감지되면 command 전체를 fail closed한다.

허용 관측은 `docker compose config --quiet`, `ps --all --quiet`, `docker inspect`, API container 내부 `HttpFetch GET`과 host loopback `/healthz`, backup artifact read/inventory, `statvfs`다. command는 backup 실행, DB write, container start/stop/restart/recreate, file create/delete와 secret-resolved Compose config 출력을 하지 않는다.

## Canonical JSON

stdout은 설명 log 없이 다음 exact shape의 JSON object 하나다. optional raw value를 알 수 없으면 key를 제거하지 않고 `null`로 둔다.

```json
{
  "formatVersion": 1,
  "observedAt": "2026-08-29T12:34:56Z",
  "services": {
    "web": {"state": "RUNNING", "health": "HEALTHY", "restartCount": 0},
    "api": {"state": "RUNNING", "health": "HEALTHY", "restartCount": 0},
    "postgres": {"state": "RUNNING", "health": "HEALTHY", "restartCount": 0}
  },
  "origin": {
    "reachable": true,
    "healthzStatus": 200
  },
  "recurring": {
    "reachable": true,
    "status": "UP",
    "enabled": true,
    "processStartedAt": "2026-08-29T12:00:00Z",
    "pollCountSinceStart": 10,
    "lastPollStartedAt": "2026-08-29T12:34:00Z",
    "lastPollCompletedAt": "2026-08-29T12:34:01Z",
    "lastPollSucceeded": true,
    "lastAdvancedOccurrenceCount": 0,
    "lastPollRuleFailureCount": 0,
    "totalRuleFailureCountSinceStart": 0,
    "consecutivePollExecutionFailures": 0,
    "lastPollExecutionFailureAt": null,
    "lastRuleFailureAt": null
  },
  "backup": {
    "markerState": "VALID",
    "createdAt": "2026-08-29T11:34:56Z",
    "ageSeconds": 3600,
    "schemaVersion": "8",
    "sizeBytes": 123456,
    "inventory": {"valid": 3, "invalid": 0, "incomplete": 0, "foreign": 0}
  },
  "filesystem": {
    "state": "AVAILABLE",
    "capacityBytes": 1000000000,
    "availableBytes": 500000000,
    "usedPercent": 50.0
  }
}
```

service `state`는 `MISSING`, `CREATED`, `RUNNING`, `PAUSED`, `RESTARTING`, `REMOVING`, `EXITED`, `DEAD`, `UNKNOWN` 중 하나다. `health`는 `HEALTHY`, `UNHEALTHY`, `STARTING`, `NONE`, `UNKNOWN` 중 하나다. service가 없으면 `MISSING/NONE/null`이며 health를 invent하지 않는다.

origin은 running Web의 실제 `NetworkSettings.Ports`가 가리키는 `127.0.0.1` port만 GET하고 redirect를 따라가지 않는다. transport failure는 `reachable=false`, `healthzStatus=null`이다. API가 stopped/unreachable이거나 internal JSON/status 계약이 잘못되면 recurring은 `reachable=false`, `status=UNREACHABLE`이고 나머지 field는 `null`이다.

backup `markerState`는 `VALID`, `MISSING`, `INVALID`, `UNAVAILABLE`이다. `last-success.json`과 실제 latest valid bundle이 일치하고 `createdAt`이 미래가 아닐 때만 age/schema/size를 채운다. inventory는 valid/invalid/incomplete/foreign 개수만 포함하며 artifact 이름, SHA-256과 path를 복사하지 않는다. filesystem `usedPercent`는 `(capacityBytes - availableBytes) / capacityBytes × 100`을 소수점 한 자리로 표시하고 stat 실패는 `UNAVAILABLE/null`이다.

## Policy evaluator

`scripts/status_tools/monitor_policy.py`는 B1 canonical snapshot과 previous non-sensitive state만 받아 다음 exact result를 만든다. raw snapshot, path, container/artifact identity와 금융 상세를 result에 복사하지 않는다.

```json
{
  "formatVersion": 1,
  "observedAt": "2026-08-29T12:34:56Z",
  "status": "OK|WARN|CRITICAL",
  "signals": [
    {
      "code": "SERVICE_PENDING",
      "severity": "WARN",
      "target": "web"
    }
  ]
}
```

`target`은 `web`, `api`, `postgres`, `recurring`의 safe allowlist가 필요한 service signal에만 있다. stable signal code는 `SERVICE_PENDING`, `SERVICE_DOWN`, `ORIGIN_PENDING`, `ORIGIN_DOWN`, `RECURRING_STARTING`, `RECURRING_NOT_RUNNING`, `RECURRING_STALE`, `RECURRING_EXECUTION_FAILED`, `RECURRING_RULE_FAILURE`, `BACKUP_MISSING`, `BACKUP_INVALID`, `BACKUP_UNAVAILABLE`, `BACKUP_STALE`, `BACKUP_INVENTORY_WARNING`, `FILESYSTEM_UNAVAILABLE`, `DISK_USAGE_WARNING`, `DISK_USAGE_CRITICAL`, `STATE_INVALID`, `STATUS_UNAVAILABLE`로 제한한다.

정책은 다음과 같다.

- Web/API/PostgreSQL의 `RUNNING/HEALTHY` 실패와 recurring operations `UNREACHABLE`은 target별 첫 observation `WARN`, 두 번째 연속 observation부터 `CRITICAL`이다. 새 정상 observation은 해당 streak만 0으로 reset한다.
- origin `reachable != true` 또는 `/healthz != 200`도 첫 observation `WARN`, 두 번째부터 `CRITICAL`이다.
- recurring scheduler는 production에서 `enabled=true`여야 한다. process age 5분 미만의 poll 0은 `RECURRING_STARTING/WARN`, 5분 이상 poll 0은 `RECURRING_NOT_RUNNING/CRITICAL`이다.
- completed poll age가 5분을 초과하면 `RECURRING_STALE/CRITICAL`이고 5분 정확히는 stale이 아니다. operations `DOWN` 또는 `lastPollSucceeded=false`는 즉시 `RECURRING_EXECUTION_FAILED/CRITICAL`이다.
- `lastPollCompletedAt`이 새로 전진한 poll만 rule failure streak를 갱신한다. failed poll 1~2개는 `WARN`, 3개부터 `CRITICAL`, 새 clean poll은 0으로 reset한다. 같은 poll snapshot을 반복 읽어도 증가하지 않는다.
- verified local backup age가 7시간 이상이면 `BACKUP_STALE/CRITICAL`이다. marker `MISSING/INVALID/UNAVAILABLE`은 age와 무관하게 `CRITICAL`, invalid 또는 incomplete inventory가 있으면 `WARN`, foreign count만으로는 signal을 만들지 않는다.
- filesystem 사용률은 80% 미만 `OK`, 80% 이상 90% 미만 `WARN`, 90% 이상 `CRITICAL`이고 `UNAVAILABLE`은 `CRITICAL`이다.

## Minimal monitor state

state는 repository/DB가 아니라 operator가 10D에서 준비할 repository 밖 dedicated directory에 둔다. directory는 현재 사용자 소유 mode `0700`, `monitor-state.json`과 persistent lock file은 `0600`, final path는 symlink가 아니어야 한다.

저장 field는 format version, `lastObservedAt`, safe target별 service failure streak, origin streak, 마지막으로 처리한 recurring poll completion timestamp, rule failure streak와 `lastOverallStatus`뿐이다. raw snapshot, container ID, artifact filename/path/hash, heartbeat URL, 사용자/Household/Member/Recurring/Account/Category ID, email, memo와 amount는 저장하지 않는다.

state는 temp file write → file `fsync` → atomic `os.replace` → state directory `fsync` 순서로 갱신한다. monitor 동시 실행은 persistent `0600` regular lock file의 non-blocking `flock`으로 차단하고 process 종료 시 kernel lock이 해제된다. corrupt/permissive/symlink/oversized state를 0으로 reset하지 않으며 `STATE_INVALID/CRITICAL` heartbeat를 보내고 기존 bytes를 보존한다.

## Uptime Kuma push worker

`scripts/monitor-production.sh`는 다음 external 값이 준비된 뒤 B1 status → evaluator → state atomic update → heartbeat 순서로 한 번 실행하는 source entrypoint다.

```bash
./scripts/monitor-production.sh \
  --project-name <exact-production-compose-project> \
  --env-file <absolute-owner-only-file-outside-repository> \
  --backup-dir <absolute-owner-only-directory-outside-repository> \
  --state-dir <absolute-owner-only-directory-outside-repository> \
  --heartbeat-config <absolute-owner-only-file-outside-repository>
```

heartbeat config는 mode `0600` regular file이며 정확히 다음 key 하나만 허용한다.

```text
STATUS_HEARTBEAT_URL=<secret Uptime Kuma push URL>
```

HTTPS 또는 loopback HTTP의 `/api/push/<token>`만 허용한다. redirect를 따르지 않고 request 5초, response 64 KiB, URL/message 크기를 제한한다. URL은 stdout/stderr/state에 출력하지 않는다. evaluator `OK/WARN`은 Kuma `up`, `CRITICAL`은 `down`이고 message는 severity와 allowlisted code/target만 포함한다. delivery 실패는 state를 되돌리거나 application/DB/backup/container를 변경하지 않고 nonzero로 종료한다. status 실패는 기존 state를 유지한 채 `STATUS_UNAVAILABLE/CRITICAL`을 전송한다.

`launchd/com.homeserver.our-ledger-monitor.plist.example`은 60초마다 repository 밖 fixed bootstrap을 호출하고 `KeepAlive`를 사용하지 않는다. 실제 bootstrap copy, heartbeat URL, state directory, LaunchAgent install/load와 Uptime Kuma monitor/email 연결은 10D에서 첫 verified production backup 뒤 별도 승인한다.

## Privacy와 failure semantics

snapshot과 error에는 다음을 포함하지 않는다.

- container ID, image registry credential, container environment와 mount host path
- DB password, Cloudflare token/JWT/cookie, env file 내용
- email, recurring/Household/User/Member/Account/Category ID 또는 이름
- memo, amount와 거래 내용
- raw operations response, exception message/stack
- absolute env/backup path, bundle/dump filename과 hash

부분 관측이 가능하면 한 subcomponent failure 때문에 다른 안전한 결과를 버리지 않는다. 다만 project/env/path/Compose authority가 불명확하면 잘못된 stack을 관측하지 않도록 nonzero로 종료한다. unknown, missing, unreachable, invalid와 unavailable을 `UP`, `HEALTHY`, current timestamp 또는 임의 0으로 바꾸지 않는다.

## Activation 경계

B2 source는 threshold, evaluator, state format, Kuma mapping과 LaunchAgent example을 확정하지만 monitor를 생성하거나 실행하지 않는다. 기본 notification authority는 Uptime Kuma push monitor와 기존 Uptime Kuma email path다. Slack, Discord webhook, Pushover, SMS, Sentry와 Prometheus/Grafana/OTel alert stack을 새로 도입하지 않는다. HomeOps Discord global switch와 ingestion도 변경하지 않는다.

10D에서 exact production target, 첫 verified backup, external owner-only path/config/bootstrap, Kuma interval/grace/email route와 rollback을 확인한 뒤 설치한다. Category나 memo 같은 사용자 행동 데이터와 raw health response를 외부 분석 서비스로 보내지 않는다.

## 검증

`scripts/verify-observability.sh`는 actual production resource 없이 exact-HEAD API/Web image, 고유 Compose project, 합성 DB credential과 owner-only backup artifact를 사용한다. canonical snapshot, recurring poll/occurrence, isolated rule failure, API unavailable, process restart reset, public actuator 404, HttpFetch non-200/network failure, privacy/read-only와 residue 0을 검증한다.

`scripts/verify-monitor-policy.sh`는 actual production resource 없이 pure threshold boundary, 독립 streak/recovery, same-poll idempotency, state path/mode/atomic update/corruption/lock, local synthetic HTTP의 Kuma up/warn/down·redirect·size·network failure와 두 plist contract를 검증한다.

Backend unit/integration은 process-local state concurrency, exception semantics, HealthIndicator와 readiness/liveness 독립을 고정한다. Python unit은 B1 authority/failure vocabulary와 policy/state/Kuma privacy allowlist를 고정한다. Hosted Full CI는 독립 `observability`와 `monitor-policy` job에서 같은 smoke를 exact HEAD로 실행한다.
