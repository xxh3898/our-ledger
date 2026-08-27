---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 06-security/privacy-model.md
  - 08-operations/backup-restore.md
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
- 비밀번호 hash만 저장
- 세션 ID와 CSRF token 로그 금지
- CSV에 내부 기술 식별정보를 최소화

## 실제 삭제

Household 전체 삭제, 사용자 탈퇴 후 데이터 삭제, backup 파기는 운영 정책 확정 후 별도 기능으로 다룬다. 출시 전 개인정보 보존기간과 파기 절차를 확정해야 한다.
