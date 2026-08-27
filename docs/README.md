---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - AGENTS.md
---

# 문서 색인

이 디렉터리는 `our-ledger`의 제품·도메인·데이터·API·화면·보안·품질·운영 계약을 보관한다. 채팅 기록이 아니라 저장소 문서를 단일 기준원으로 사용한다.

## 읽기 순서

1. [`00-overview/product-overview.md`](00-overview/product-overview.md)
2. [`01-product/v1-scope.md`](01-product/v1-scope.md)
3. [`02-domain/transaction.md`](02-domain/transaction.md)
4. [`03-data/erd.md`](03-data/erd.md)
5. [`07-quality/financial-invariants.md`](07-quality/financial-invariants.md)
6. 작업 Issue에 연결된 상세 문서와 ADR

## 디렉터리

| 경로 | 내용 |
|---|---|
| `00-overview` | 제품 개요, 용어, 기술 기준, 로드맵, 개발 흐름 |
| `01-product` | 제품 원칙, V1 범위, 사용자 흐름, 기능 매트릭스, 벤치마킹 |
| `02-domain` | Household, 거래, 계좌, 예산, 목표 등 도메인 규칙 |
| `03-data` | ERD, 스키마 제약, ledger, 보존 정책 |
| `04-api` | REST 규칙, 오류 계약, 필터·페이지네이션 |
| `05-frontend` | 정보구조, 핵심 화면, PWA 정책 |
| `06-security` | 인증, 권한, 개인정보 모델 |
| `07-quality` | 테스트, 재무 불변식, 인수 기준 |
| `08-operations` | 배포, 백업·복구, 관측성 |
| `09-decisions` | Accepted ADR와 ADR 템플릿 |

## 문서 상태

- `draft`: 논의 또는 검증이 남음
- `active`: 현재 구현 기준
- `deprecated`: 더 이상 새 구현에 사용하지 않음
- `superseded`: 다른 문서나 ADR로 대체됨

구현이 계약과 달라지면 코드를 기준으로 문서를 사후 수정하지 않는다. 먼저 변경 필요성을 검토하고, 계약 변경이 맞다면 문서와 ADR을 같은 Pull Request에서 갱신한다.
