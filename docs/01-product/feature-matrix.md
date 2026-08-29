---
status: active
version: 0.9
last_updated: 2026-08-29
related:
  - 00-overview/roadmap.md
  - ADR-008
---

# 기능 매트릭스

| 기능 | Slice | Backend | Frontend | 핵심 계약 |
|---|---:|---:|---:|---|
| Access 인증·User 매핑 | 1 | O | O | Access JWT 검증, 내부 User/Household 권한 확인 |
| Account/Category | 2 | O | O | 개인·공동 소유권 |
| 수입·지출 | 2 | O | O | entry 1개, amount 양수 |
| 이체·카드 | 3 | O | O | source/destination entry |
| 달력·필터 | 4 | O | O | 월 범위·안정 정렬 |
| 예산 | 5 | O | O | 월 독립, 환불 반영 |
| 통계 | 6 | O | O | 원장 파생, drill-down |
| 반복거래 | 7 | O | O | idempotency |
| 결혼자금 | 8 | O | O | Account 연결, 중복 입력 금지 |
| 자산 흐름 | 9 | O | O | ASSET-LIABILITY |
| CSV 내보내기 | 10A | O | O | current Household, canonical Entry, formula 방어, no-store |
| Immutable runtime | 10C-1 | O | O | multi-stage image, same-origin Nginx, production Compose/smoke |
| Backup/Restore safety | 10C-2A | O | - | custom dump, atomic integrity bundle, isolated restore drill |
| Observability/Alert harness | 10C-2B | - | - | health, backup freshness, scheduler/disk signal |
| PWA 설치 | 10B | - | - | 최종 한글 이름·production icon 결정까지 HOLD |
| Production activation | 10D | - | - | Access/Tunnel, secret, bootstrap, deploy |

## Slice 5 Budget 구현

- 월 Budget identity: Household timezone의 월, HOUSEHOLD/PERSONAL/SHARED, nullable EXPENSE Category
- Backend read model: Budget row 유무와 무관한 기본 Scope 사용액, 실제 생성된 Category Budget
- Frontend: Budget 하단 destination, 월 history, 생성·수정·삭제, 사용액 drill-down
- 재무 기준: 카드 구매 EXPENSE 포함, 카드대금 TRANSFER·INCOME·논리삭제 제외, REFUND 차감
- 제외: 자동 이월·자동 복사·거래 차단·추천·Statistics 구현

## Slice 6 Statistics 구현

- Backend read model: current/comparison summary와 주체·Category·PRIMARY Account·calendar month breakdown
- 재무 기준: NORMAL INCOME, NORMAL EXPENSE - REFUND EXPENSE, 저축 Account 순이체, income 0 저축률 null
- Frontend: 이번 달 기본값, preset/custom 기간, 실제 Member/공동 Scope, canonical URL/history, semantic table/list
- Drill-down: 기존 Transaction 목록과 impact가 0이 아닌 savings activity endpoint
- 제한: 저축은 ALL에만 제공하며 개인·공동 Account ownership 귀속, aggregate persistence/cache/index migration 없음

## Slice 7 Recurring 구현

- Backend: DAILY/WEEKLY/MONTHLY/YEARLY + interval, Household local time, cursor 기반 bounded catch-up
- 원장: due occurrence의 일반 Transaction/Entry만 재무 상태에 반영, generated lineage와 deleted row 포함 idempotency
- 동시성: rule row lock + due 재확인 + database unique, occurrence별 transaction과 one-rule failure isolation
- lifecycle: optimistic rule edit, pause/resume no-backfill, active Account/Category/Group reference 보호
- Frontend: Settings의 active/paused/ended 목록, 생성·수정·중지·재개 Sheet, Calendar/통계 `반복` text provenance
- 제한: recurring REFUND, `auto_post=false`, pending 승인, 알림, 전용 Bottom Navigation tab 없음

## Slice 8 Marriage Goal 구현

- Backend: Household MARRIAGE Goal 생성/수정, eligible 실제 Account 연결/해제, optimistic version
- 원장: current Account balance 합, current link와 `linked_at` 기준 Goal 경계 TRANSFER 순저축
- 동시성: Household partial unique, Account assignment unique, posting과 같은 Account row lock의 연결 snapshot
- 지표: raw 달성률, 남은 금액, 현재 월, 6개월 추세, 완료 3개월 평균, 명시적 projection 상태, 최근 근거
- Frontend: Home actual/empty card, `?screen=goal` 상세, create/edit/link Sheet, unlink 확인, accessible SVG/table
- 제한: CUSTOM UI, 수동 기여금, aggregate cache, Goal 삭제, 새 Bottom tab, Assets/production asset 없음

## Slice 9 Assets 구현

- Backend: active·archived Account와 유효 Entry에서 current balance를 batch 파생하는 Household read model
- 지표: 총자산, 총부채, 순자산과 actual Member PERSONAL/SHARED 소유 소계
- 추이: Household timezone의 직전 11개 완료 월말과 현재 한 점, opening date 이전 Account 기여 0
- Frontend: Assets destination, canonical 소유 filter URL/history, accessible SVG/table, ASSET/LIABILITY Account 목록
- 일관성: repeatable-read snapshot, current point와 current summary 일치, Goal link/unlink로 원장 불변
- 제한: aggregate persistence/cache, migration, Account mutation 재설계, Goal 지표 병합, CSV/PWA/production 없음

## Slice 10A CSV Export 구현

- Backend: 필수 `from/to`, 시작일 포함 최대 3,653일, Household timezone 범위의 동기 CSV attachment
- 원장: 미삭제 Transaction당 한 row, canonical Entry fail-closed, REFUND·Recurring provenance와 archived reference 유지
- 형식: 한국어 19개 고정 column, UTF-8 BOM, RFC 4180 CRLF/quote, spreadsheet formula prefix 방어
- Frontend: Settings의 기간 form, pending/error/success, 안전한 filename fallback, Blob URL 즉시 회수
- 보안: CurrentHousehold만 사용, `no-store`/`nosniff`, `lastFour`·email·credential 비노출
- 제한: import, XLSX, 세부 filter, async/history/temp file, PWA, backup 실행, production activation 없음

## Slice 10C-1 Immutable Runtime Harness 구현

- Image: Java 25 JDK→Distroless Java 25 API와 Node 24 build→Nginx Web multi-stage, base manifest digest 고정
- Nginx: non-root 8080, SPA/static과 `/api/**` same-origin, API/CSV no-store, hashed asset immutable, `/actuator/**` 차단
- Spring: `production` profile, env datasource, Flyway, JPA validate, Cloudflare 필수 설정, local identity/자동 bootstrap fail-closed
- Compose: Web loopback-only publish, API/DB host port 없음, PostgreSQL named volume/internal network, app read-only/capability hardening
- 검증: 고유 project·임시 port·합성 설정·disposable volume의 clean build/start/restart/graceful stop와 residue 0
- 제한: PWA, image push, Cloudflare/Tunnel, 실제 secret/User/DB, backup/restore, observability, deploy 없음

## Slice 10C-2A Backup/Restore Safety Gate 구현

- Backup: existing healthy PostgreSQL 18.6의 online `pg_dump` custom archive, API/Web restart와 DB volume direct read 없음
- Artifact: owner-only partial bundle, nonzero/`PGDMP`/`pg_restore --list`/SHA-256/metadata 검증 뒤 atomic directory rename
- Latest success: 비민감 `last-success.json`을 verified success 뒤에만 atomic 갱신하고 failure는 이전 marker 보존
- Restore: 고유 source/target Compose project와 별도 disposable volume, synthetic non-empty fixture, fail-fast `pg_restore`
- 검산: Flyway V1~V8, core row/Transaction/Entry/Refund lineage, ASSET/LIABILITY/순자산, FK/unique, production API JPA/readiness
- 제한: 실제 production backup/restore, schedule, retention 삭제, 외부 destination/암호화/복제, observability/alert, deploy 없음

## 공통 요구

모든 Slice는 다음을 포함한다.

- Household 경계 테스트
- 주요 오류 계약
- 문서 동기화
- Hosted CI
- 모바일 기본 접근성
- 재무 불변식 회귀 여부 확인

인증이 필요한 Slice는 Cloudflare Access production 계약과 local/CI 테스트 identity 경로를 혼동하지 않는다. production에서 Access JWT 검증 우회는 허용하지 않는다.
