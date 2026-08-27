---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - AGENTS.md
---

# 아키텍처 결정 기록

## Accepted ADR

| ADR | 결정 |
|---|---|
| [ADR-001](ADR-001-household-boundary.md) | Household를 tenant boundary로 사용 |
| [ADR-002](ADR-002-transaction-account-entry.md) | Transaction과 Account Entry 분리 |
| [ADR-003](ADR-003-personal-shared-scope.md) | PERSONAL/SHARED와 Owner/Payer 분리 |
| [ADR-004](ADR-004-refund-model.md) | 음수 금액 대신 REFUND Transaction |
| [ADR-005](ADR-005-recurring-generation.md) | 반복규칙이 실제 Transaction 생성 |
| [ADR-006](ADR-006-goal-account-model.md) | Goal을 실제 Account와 연결 |
| [ADR-007](ADR-007-session-authentication.md) | JWT 대신 서버 세션 인증 |

새 결정은 [`ADR-template.md`](ADR-template.md)를 복사해 작성한다. 기존 결정을 변경할 때 원문을 지우지 않고 새 ADR에서 supersede 관계를 기록한다.
