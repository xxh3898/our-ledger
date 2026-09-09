---
status: active
version: 0.2
last_updated: 2026-09-09
related:
  - 07-quality/testing-strategy.md
  - 08-operations/deployment.md
  - ADR-008
  - ADR-009
---

# Fast PR CI와 Full CI 변경 영향 계약

Issue #122는 dev 대상 PR의 피드백 시간을 줄이며, dev에 합쳐진 source와 main/release는 기존 Full 검증을 유지한다. Issue #123의 Docker layer cache는 이 job 선택 계약을 바꾸지 않는다. job 사이 exact-HEAD image 공유와 heavy verifier 내부 최적화는 별도 Issue #124~#125 범위다.

## 진입점과 결과

| 진입점 | 분류 | 실행 |
| --- | --- | --- |
| `full-ci.yml` 직접 실행, `pull_request`, base `dev` | exact base SHA와 PR head SHA의 변경 경로 | repository → 선택 job → CI gate |
| `pull_request`, base `main` | Full | 기존 16개 job → CI gate |
| `push: dev` | Full | 기존 16개 job → CI gate |
| `workflow_dispatch` | Full | 기존 16개 job → CI gate |
| 다른 workflow의 `workflow_call` | Full | 기존 16개 job → CI gate |
| 이벤트/호출자/diff를 확정할 수 없음 | Full fallback | 기존 16개 job → CI gate |

workflow 이름은 `Full CI`를 유지하고 기존 job/check 이름도 보존한다. repository job은 항상 시작해 기존 구조·문서·migration byte·Compose 검증과 분류 회귀 테스트를 수행한다. 선택 job은 repository의 `run_backend`, `run_frontend`, `run_full` 출력을 사용한다. 최종 `CI gate`는 `always()`와 기존 16개 job의 `needs`를 사용하며 다음을 모두 확인한다.

- repository 성공
- 알려진 category와 해당 category에 맞는 exact string flags
- 선택된 job 전부 `success`
- 생략 대상 전부 `skipped`

job 실패·취소·예상 밖 skip, 분류 출력 손상, 누락된 dependency를 성공으로 숨기지 않는다. 분류 프로그램 실행 자체가 실패하면 workflow가 Full flags를 출력하며, repository 출력 자체가 없으면 downstream `!= 'false'` 조건이 Full 쪽으로 동작한다. repository가 실패하면 최종 gate도 실패한다.

`paths`/`paths-ignore`로 workflow 전체를 생략하지 않는다. 2026-09-09 live ruleset `22201925`는 main/dev의 PR-only·삭제 금지·non-fast-forward 금지를 적용하지만 required status-check 목록은 설정하지 않았다. 이 변경은 repository 설정을 수정하지 않는다. 향후 필수 check를 지정할 때는 모든 category에서 완료되는 `CI gate`를 사용할 수 있다.

PR concurrency group은 workflow 이름과 PR 번호를 사용하며 `cancel-in-progress`는 PR 이벤트에서만 true다. 비PR은 각 run ID의 독립 group과 false를 사용하므로 기존 dev/release 실행의 취소·직렬화 의미를 바꾸지 않는다. `deploy.yml`과 `publish-release.yml`의 `our-ledger-production`, `cancel-in-progress: false`, deploy kill switch와 release authority는 변경하지 않는다.

## 분류 입력과 fail-safe

`scripts/ci_tools/change_classifier.py`는 검증된 40자리 base/head SHA에 `git diff --raw --no-renames --no-ext-diff --no-textconv -z base...head --`를 적용한다. API 페이지 제한이나 최신 PR metadata 재조회에 의존하지 않는다. checkout은 전체 이력을 가져온다.

rename 감지를 끄므로 이전 경로 삭제와 새 경로 추가를 모두 검사한다. 운영 source를 frontend로 옮겨도 이전 운영 경로가 사라지지 않는다. 삭제된 파일도 경로 분류에 포함한다. regular non-executable file 이외 mode, symlink/gitlink/type 변경, 잘못된 UTF-8/NUL framing/status, Git timeout/failure, 잘못된 SHA와 empty diff는 Full이다. base branch에서만 전진한 변경은 three-dot 비교에서 PR 변경으로 오인하지 않는다.

reusable workflow의 `github` context는 caller의 context를 사용하므로 `event_name`만으로 직접 PR 실행 여부를 판단하지 않는다. Fast 경로는 caller `github.workflow_ref`가 해당 repository의 `.github/workflows/full-ci.yml@refs/pull/<번호>/merge`와 정확히 일치할 때만 허용한다. 다른 caller, 누락된 context는 Full이다. 이 구분은 [GitHub의 reusable workflow context 계약](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#github-context)에 따른다.

## 경로 matrix

아래 허용 목록 밖의 새 경로나 확장자는 먼저 Full로 처리한다. 설명용 Markdown은 frontend/backend 경로에 동반되어도 source category를 증가시키지 않으며, authority 문서는 Markdown보다 우선 판정한다.

| category | 경로 예시와 경계 | 선택 job | 생략 job 및 근거 |
| --- | --- | --- | --- |
| docs-only | root/docs/frontend/backend README, `docs/00-overview`, `01-product`, `02-domain`, `05-frontend`, `07-quality` 아래 Markdown만 | repository, CI gate | backend/frontend/heavy: 실행 source·build context·runtime authority 변경 없음 |
| frontend-only | `frontend/src/`의 TS/TSX/CSS + 위 설명 docs | repository, frontend, CI gate | backend/heavy: 일반 화면 source는 Nginx/Compose/API profile·migration·host lifecycle을 바꾸지 않음 |
| backend-only | 기존 `account/assets/budget/calendar/category/export/goal/statistics/transaction` package의 직접 Java 파일과 기존 test package의 직접 `*Test.java` + 설명 docs | repository, backend, CI gate | frontend/heavy: domain build/test·Flyway·JPA·REST Docs·인증/Household 회귀는 전체 Backend CI가 검증 |
| ops-runtime | `infra/`, `scripts/`, `.github/`, `launchd/`, Compose, `.env*`, `.dockerignore*`, `runtime-*`, `AGENTS.md` | 기존 16개 + CI gate | 없음: 배포·검증·설정 authority |
| ops-runtime | frontend package/lockfile/config/index/public/manifest/build script 및 TS/TSX/CSS 이외 새 source asset | 기존 16개 + CI gate | 없음: Docker COPY allowlist, dependency, build 및 실제 runtime output에 연결 |
| ops-runtime | backend build/Gradle, main/test resources, Flyway migration, security/identity/household/bootstrap/ops/recurring package, application entrypoint | 기존 16개 + CI gate | 없음: 보안, data, production profile, bootstrap/scheduler authority |
| ops-runtime | backend 파일 이름의 Config/Security/Bootstrap/Migration/Profile/Scheduler/Operational/Health/Authentication/Authorization/Csrf/Identity/Household/Filter/Guard/Controller/Request/Response/Application, 대소문자 무관 | 기존 16개 + CI gate | 없음: 다른 허용 package 아래 배치된 보안/config/API 경로도 승격 |
| ops-runtime | `docs/03-data`, `04-api`, `06-security`, `08-operations`, `09-decisions` | 기존 16개 + CI gate | 없음: DB/API/security/deployment/Accepted ADR authority |
| mixed/unknown | frontend + backend, 모르는 package/경로, 비정상 경로, 빈 diff, 분류 실패 | 기존 16개 + CI gate | 없음: 의존성을 확정하지 못하면 Full fallback |

frontend-only는 기존 `verify-frontend.sh` 전체를 실행한다. lint, typecheck, 모든 component/integration test, production build가 유지되며 build에는 manifest `start_url=/`, `scope=/`, `display=standalone`, source/build byte correspondence와 HTML link 검증이 포함된다. package/config/index/manifest/Docker source 변경은 Fast 허용 대상이 아니다. 따라서 이 경로에서는 일반 TS/CSS를 다시 build하는 Docker-heavy job을 PR 단계에서 생략하고 dev post-merge에서는 실행한다. 모바일 #132/#133 등의 기존 frontend 회귀도 그대로 실행된다.

backend-only는 일부 테스트 선택이 아닌 기존 `./gradlew --no-daemon clean check` 전체를 실행한다. 실제 PostgreSQL Testcontainers, clean Flyway, JPA validate, 도메인·재무 불변식·Household·보안·REST Docs 검증을 줄이지 않는다. migration/resources/API DTO/controller/production 관련 source는 Full로 승격한다.

## 기존 CI graph와 검증 의존성

변경 전 `full-ci.yml`의 16개 job은 모두 `needs` 없이 병렬 시작했다. 변경 후 repository가 분류를 출력하고 나머지 15개 job은 해당 flags를 기다린다. job 삭제는 없으며 실제 verifier 본문, Backend/Frontend reusable workflow, `scripts/verify.sh`의 19개 gate는 그대로다.

duration은 [PR #150의 run 34296805373](https://github.com/xxh3898/our-ledger/actions/runs/34296805373)의 job started/completed timestamp 차이다. 공통 trigger는 위 표의 PR/dev push/dispatch/reusable이며, Full에서는 모두 실행한다.

| job | 시간 | 직접 source/검증 입력 | 증명하는 불변식 | Fast 생략 가능 category |
| --- | --- | --- | --- | --- |
| repository | 4초 | repo metadata, docs, migrations, Compose, validation source | 구조·secret 후보·Issue Form·링크·적용 migration byte·Compose isolation | 없음 |
| backend / backend | 75초 | backend source/tests/resources/Gradle | clean build, PostgreSQL/Flyway/JPA, API/domain/security | docs, frontend |
| frontend / frontend | 32초 | frontend source/tests/package/config/manifest | lint/typecheck/tests/build, canonical app-start | docs, backend |
| backup-docker-authority | 6초 | backup core, fixed Docker executable test | fixed CLI/Compose authority와 hostile env 거부 | docs, frontend, 제한된 backend |
| production-runtime | 232초 | API/Web Dockerfile, Nginx, Compose, backend profiles/resources, frontend build | immutable hardening, proxy, same-image migration/JPA, clean failure, cleanup | docs, 일반 frontend, 제한된 backend |
| production-bootstrap | 357초 | backend bootstrap/security/profiles/resources, API image, Compose | production one-shot 2/1/2 identity, rerun/failure state 보존 | docs, frontend, 제한된 backend |
| fresh-host-bootstrap | 150초 | host/fresh bootstrap source, runtime artifact, API/Web/Compose | durable recovery, migration/bootstrap/readiness/backup ordering | docs, 일반 frontend, 제한된 backend |
| host-state | 5초 | host state/source, backup core | fixed root, shared lock, exact immutable identity/state | docs, frontend, 제한된 backend |
| fixed-bootstrap | 3초 | fixed wrappers, launchd, manifest/detector | env clearing, exact entrypoint/args/schedule | docs, frontend, 제한된 backend |
| runtime-config-evolution | 11초 | manifest/Dockerfile/runtime source, host bridge | V1/V2 archive shape, digest/content identity, fail-closed extraction | docs, frontend, 제한된 backend |
| host-deploy-transaction | 10초 | host deploy/backup/reporter source | lock/quiesce/backup/migration/cutover/recovery와 token boundary | docs, frontend, 제한된 backend |
| backup-restore | 174초 | backup core/tooling/fixture, API/DB migration image | real dump/restore, checksum/financial equality, previous 보존 | docs, frontend, 제한된 backend |
| offsite-backup | 5초 | offsite source, fixed wrapper, age, launchd | pinned encrypt/decrypt, atomic no-replace, plaintext/state 보존 | docs, frontend, 제한된 backend |
| observability | 161초 | status/backup tooling, recurring operational source, API/Web/Compose | read-only status, privacy, recurring health와 public actuator 비노출 | docs, 일반 frontend, 제한된 backend |
| monitor-policy | 7초 | status policy/worker/tests, launchd | synthetic alert/retention/HomeOps, mutation 없는 source harness | docs, frontend, 제한된 backend |
| release-transport | 7초 | deploy/publish workflows, release helper/detector, runtime artifact | release SHA/digest, kill switch, fixed transport, ARM64 manifest archive | docs, frontend, 제한된 backend |

## Before/After evidence

변경 전 공통 기준은 `bb2e85fd46607c32abaa32001a2cbaf72f1b56b3`의 16-job graph다. workflow wall time은 `updated_at - created_at`이며 queue/setup/후처리를 포함하고, critical job time은 job의 `completed_at - started_at`이다. 서로 다른 runner/cache/queue 상태를 동일 조건 benchmark로 해석하지 않는다.

| representative PR | exact HEAD | run | Before wall | critical path |
| --- | --- | --- | --- | --- |
| frontend + 설명 docs #150 | `5c3ef64bd022ca6e0148b7cf95ff44c607a43953` | [34296805373](https://github.com/xxh3898/our-ledger/actions/runs/34296805373) | 361초 | production-bootstrap 357초 |
| 일반 mixed feature #142 | `9d46b1aa76cae8cdededcaf87181bfa3e6a5cfde` | [33645283102](https://github.com/xxh3898/our-ledger/actions/runs/33645283102) | 407초 | production-bootstrap 403초 |
| ops #118 | `aee119f84f6dc3c9ed48dbca29f6d50f31f4c0f5` | [33582273343](https://github.com/xxh3898/our-ledger/actions/runs/33582273343) | 405초 | production-bootstrap 400초 |
| 현재 graph의 docs-only | 해당 없음 | NO_BASELINE_EVIDENCE | 미확인 | 미확인 |
| 현재 graph의 backend-only | 해당 없음 | NO_BASELINE_EVIDENCE | 미확인 | 미확인 |

역사적 docs PR #3의 [33067823867](https://github.com/xxh3898/our-ledger/actions/runs/33067823867)은 50초지만 당시 3개 job이었으므로 현재 baseline에 넣지 않는다.

| Issue 목표 | After evidence |
| --- | --- |
| docs-only <30초 | NOT_YET_MEASURED |
| frontend-only <1분 | NOT_YET_MEASURED |
| backend-only <2분 | NOT_YET_MEASURED |
| normal feature <3분 | NOT_YET_MEASURED; mixed/unknown은 Full 보존 |

Issue #122 source PR은 workflow/scripts를 변경해 `ops-runtime`으로 분류되므로 실제 Hosted run은 Full fallback을 검증한다. 그 run의 exact HEAD·category·wall time·critical path와 최종 결과는 PR 검증란에 기록한다. 이 한 run으로 docs/frontend/backend의 Hosted 실행·취소 동작이나 시간 목표 달성을 주장하지 않는다. 빠른 경로는 deterministic source matrix와 실제 temporary Git diff, 최종 gate failure matrix로 검증하고 추후 해당 category PR의 Hosted evidence로 보완한다.

## 회귀 검증

`check-repo.sh`와 이에 연결된 local `verify.sh` 및 모든 Hosted repository job에서 Python 표준 라이브러리 테스트를 실행한다.

- docs/frontend/backend/migration/ops/mixed/unknown job 선택
- build/security/API/DB/runtime authority의 Full 승격
- rename/delete, symlink/type/executable mode, empty/malformed/Git failure
- main PR, dev push, dispatch, 다른 reusable caller의 Full
- gate dependency exact set, selected failure/cancel/skip, unselected unexpected execution, malformed output 거부
- 기존 16개 job와 local 19개 entrypoint, 항상 완료되는 gate, PR-only concurrency, production serialization 보존

전체 검증의 source 의미, release/production 권한과 physical device acceptance 구분은 [테스트 전략](testing-strategy.md) 및 기존 Accepted ADR을 따른다.

## Docker cache와 job 선택의 독립성

Issue #123은 위 category, `run_*` 출력, 기존 job/check/CI gate와 concurrency를 유지한다. repository의 별도 `docker_cache_mode` 출력은 build 방식만 선택하며 job을 생략할 수 없다. cache runtime/Buildx 준비 step 실패는 원래 verifier의 no-cache build로 이어지고 실제 verifier의 실패는 숨기지 않는다. dev push는 계속 Full이며 main/release/dispatch/local 기본값은 cache disabled다. production-runtime clean 2개와 fresh-host 합성 runtime build 1개를 포함한 총 11개 build를 유지한다.

API/Web 캐시 적용 6개 호출, fresh-host-bootstrap 단일 writer job, generation/namespace와 cold/warm evidence 기준은 [CI Docker layer cache 계약](testing-strategy.md#ci-docker-layer-cache)을 따른다. runtime-config는 기존 0.40~1.94초 build에 약 4초의 Buildx 준비 비용이 추가되므로 `NOT_APPLIED_WITH_JUSTIFICATION`으로 제외하고 direct build 3개를 유지한다. cache 전 기준인 PR #152 Full run [34357252467](https://github.com/xxh3898/our-ledger/actions/runs/34357252467)은 workflow 432초, critical production-bootstrap 408초였고, dev push [34360329100](https://github.com/xxh3898/our-ledger/actions/runs/34360329100)의 exact head `406ff7432af67e68cbd4f1fb63edd52942ba07d8`는 workflow 340초, critical job 317초였다. 이는 서로 다른 runner/queue의 관측값이며 cache 적용 효과로 해석하지 않는다. 새 exact-head Hosted cold/warm run과 실제 build 구간 비교 전 성능 개선은 미확인이다.
