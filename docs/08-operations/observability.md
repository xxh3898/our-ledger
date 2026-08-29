---
status: active
version: 0.5
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

Slice 10C-2B1은 existing production-like runtime과 10C-2A verified backup marker를 변경하지 않고 읽는 operational status harness를 구현한다. `production-status.sh`가 Web/API/PostgreSQL, loopback Nginx, process-local recurring scheduler, backup freshness/inventory와 backup filesystem을 canonical JSON object 하나로 결합한다.

실제 Mac mini production에서 status command를 실행하거나 cron/launchd, Uptime Kuma/Netdata, evaluator, threshold 또는 알림 채널을 활성화하지 않았다. B1은 raw observation interface와 synthetic local/Hosted gate까지만 제공한다. stale/disk/retry 숫자와 monitor/channel activation은 10C-2B2 또는 10D의 별도 운영 승인 대상이다.

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

## Privacy와 failure semantics

snapshot과 error에는 다음을 포함하지 않는다.

- container ID, image registry credential, container environment와 mount host path
- DB password, Cloudflare token/JWT/cookie, env file 내용
- email, recurring/Household/User/Member/Account/Category ID 또는 이름
- memo, amount와 거래 내용
- raw operations response, exception message/stack
- absolute env/backup path, bundle/dump filename과 hash

부분 관측이 가능하면 한 subcomponent failure 때문에 다른 안전한 결과를 버리지 않는다. 다만 project/env/path/Compose authority가 불명확하면 잘못된 stack을 관측하지 않도록 nonzero로 종료한다. unknown, missing, unreachable, invalid와 unavailable을 `UP`, `HEALTHY`, current timestamp 또는 임의 0으로 바꾸지 않는다.

## Threshold와 후속 activation

B1 collector는 raw snapshot만 생성하며 backup stale 시간, recurring poll stale 시간, disk 임계치, retry/연속 실패 횟수를 production default로 확정하지 않는다. metrics exporter/dashboard, external health monitor, notification channel, backup/status schedule과 external encrypted replication도 설치하지 않는다.

10C-2B2 또는 10D에서 실제 workload, RPO/RTO, 저장공간과 HomeOps 운영 경계를 확인한 뒤 evaluator와 channel을 별도로 승인한다. 재무 Category나 memo 같은 사용자 행동 데이터를 외부 분석 서비스로 보내지 않는다.

## 검증

`scripts/verify-observability.sh`는 actual production resource 없이 exact-HEAD API/Web image, 고유 Compose project, 합성 DB credential과 owner-only backup artifact를 사용한다. canonical snapshot, recurring poll/occurrence, isolated rule failure, API unavailable, process restart reset, public actuator 404, HttpFetch non-200/network failure, privacy/read-only와 residue 0을 검증한다.

Backend unit/integration은 state concurrency, exception semantics, HealthIndicator와 readiness/liveness 독립을 고정한다. Python unit은 authority, failure vocabulary, backup/filesystem, exact JSON allowlist와 mutation-free command set을 고정한다. Hosted Full CI는 독립 `observability` job에서 같은 smoke를 exact HEAD로 실행한다.
