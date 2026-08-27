---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 00-overview/roadmap.md
---

# 기능 매트릭스

| 기능 | Slice | Backend | Frontend | 핵심 계약 |
|---|---:|---:|---:|---|
| 로그인·세션 | 1 | O | O | Household 권한 확인 |
| Account/Category | 2 | O | O | 개인·공동 소유권 |
| 수입·지출 | 2 | O | O | entry 1개, amount 양수 |
| 이체·카드 | 3 | O | O | source/destination entry |
| 달력·필터 | 4 | O | O | 월 범위·안정 정렬 |
| 예산 | 5 | O | O | 월 독립, 환불 반영 |
| 통계 | 6 | O | O | 원장 파생, drill-down |
| 반복거래 | 7 | O | O | idempotency |
| 결혼자금 | 8 | O | O | Account 연결, 중복 입력 금지 |
| 자산 흐름 | 9 | O | O | ASSET-LIABILITY |
| CSV/PWA/배포 | 10 | O | O | export 보안, API cache 금지 |

## 공통 요구

모든 Slice는 다음을 포함한다.

- Household 경계 테스트
- 주요 오류 계약
- 문서 동기화
- Hosted CI
- 모바일 기본 접근성
- 재무 불변식 회귀 여부 확인
