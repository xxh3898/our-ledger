---
status: active
version: 0.5
last_updated: 2026-08-29
related:
  - 06-security/privacy-model.md
  - 08-operations/backup-restore.md
  - ADR-008
---

# 데이터 보존과 삭제

## 원칙

재무 데이터는 단순 UI 삭제보다 복구 가능성과 감사 가능성이 중요하다. 그러나 불필요한 개인정보를 영구 보관하지 않는다.

## Transaction

- 사용자 삭제는 논리삭제다.
- 삭제 시 `deleted_at`, `deleted_by`를 기록한다.
- 기본 조회, 잔액, 통계, Budget, Goal에서 제외한다.
- 복원 UI는 V1 MUST가 아니지만 운영 복구 가능성은 유지한다.

## 기준정보

Account, Category, Category Group은 거래가 연결되면 archive한다. archive된 항목은 새 입력 선택지에서 제외하고 과거 내역에는 표시한다.

## 감사 필드

주요 변경 엔티티는 `created_at`, `updated_at`, `created_by`, `updated_by`를 가능한 범위에서 가진다. 상세 변경 이력 테이블은 V1에 도입하지 않는다.

## 민감정보

- 전체 계좌번호·카드번호 미저장
- 애플리케이션 사용자 비밀번호와 `password_hash` 미저장
- `Cf-Access-Jwt-Assertion`, `CF_Authorization` cookie, CSRF credential 미저장·로그 금지
- CSV에 내부 기술 식별정보를 최소화

## CSV Export

- CSV는 current Household의 요청 시점 유효 Transaction에서 메모리로 생성하며 export table, history, cache, server temp file을 남기지 않는다.
- 논리삭제 Transaction은 제외하고 archived Account/Category 이름은 과거 거래 검산을 위해 유지한다.
- Transaction ID와 REFUND 원거래 ID는 lineage 검산에 필요한 최소 기술 ID로 포함한다.
- Account/Card 전체 번호, `lastFour`, email, Access/CSRF credential은 포함하지 않는다.
- CSV는 사용자가 내려받은 뒤 browser와 사용자 기기의 보존 정책을 따르며 서버 운영 backup이나 삭제 복원의 대체물이 아니다.

## PostgreSQL Backup Artifact

- 10C-2A backup은 logical delete row와 Flyway history를 포함한 PostgreSQL custom archive이므로 CSV보다 민감하고 복구 범위가 넓다.
- 검증된 dump, checksum, metadata는 owner-only atomic bundle 하나로 취급한다. `last-success.json`은 dump 내용을 복제하지 않고 최신 성공 시각·schema·size·hash·파일명만 가리킨다.
- metadata와 marker에는 email, memo, Category/Account 내용, DB password, token/cookie와 resolved Compose config를 넣지 않는다.
- strict inventory는 valid/invalid/incomplete/foreign artifact를 분류만 하며 삭제하지 않는다.
- accepted dry-run plan은 latest verified bundle 4개와 지난 7 KST calendar day마다 06:00 이후 첫 verified bundle 1개를 중복 없이 `keep`으로 분류한다. 나머지 verified bundle만 `pruneCandidates`이며 invalid/future, incomplete, foreign과 symlink는 삭제 후보에서 제외한다.
- `retention-plan` helper는 deterministic JSON만 출력하고 artifact, marker와 backup directory를 변경하지 않는다. `pruneCandidates`는 최소 7일 운영 관찰, age ciphertext remote decrypt, isolated restore drill과 별도 production deletion 승인 전에는 삭제하지 않는다.
- future offsite는 verified local snapshot을 tar stream으로 age public recipient에 암호화하고 local ciphertext와 iCloud `.partial`/final SHA-256을 검증한 뒤에만 성공으로 인정한다. raw dump를 외부에 직접 복사하지 않고 private age identity를 repository나 Mac mini plaintext file에 두지 않는다.

## 실제 삭제

Household 전체 삭제, 사용자 탈퇴 후 데이터 삭제, backup 파기는 운영 정책 확정 후 별도 기능으로 다룬다. 출시 전 개인정보 보존기간과 파기 절차를 확정해야 한다.
