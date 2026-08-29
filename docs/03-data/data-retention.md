---
status: active
version: 0.3
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

## 실제 삭제

Household 전체 삭제, 사용자 탈퇴 후 데이터 삭제, backup 파기는 운영 정책 확정 후 별도 기능으로 다룬다. 출시 전 개인정보 보존기간과 파기 절차를 확정해야 한다.
