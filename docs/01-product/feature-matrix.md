---
status: active
version: 0.3
last_updated: 2026-08-28
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
| CSV/PWA/배포 | 10 | O | O | export 보안, API cache 금지, Access/Tunnel 보호 |

## Slice 5 Budget 구현

- 월 Budget identity: Household timezone의 월, HOUSEHOLD/PERSONAL/SHARED, nullable EXPENSE Category
- Backend read model: Budget row 유무와 무관한 기본 Scope 사용액, 실제 생성된 Category Budget
- Frontend: Budget 하단 destination, 월 history, 생성·수정·삭제, 사용액 drill-down
- 재무 기준: 카드 구매 EXPENSE 포함, 카드대금 TRANSFER·INCOME·논리삭제 제외, REFUND 차감
- 제외: 자동 이월·자동 복사·거래 차단·추천·Statistics 구현

## 공통 요구

모든 Slice는 다음을 포함한다.

- Household 경계 테스트
- 주요 오류 계약
- 문서 동기화
- Hosted CI
- 모바일 기본 접근성
- 재무 불변식 회귀 여부 확인

인증이 필요한 Slice는 Cloudflare Access production 계약과 local/CI 테스트 identity 경로를 혼동하지 않는다. production에서 Access JWT 검증 우회는 허용하지 않는다.
