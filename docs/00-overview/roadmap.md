---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 01-product/feature-matrix.md
  - 07-quality/acceptance-criteria.md
---

# 개발 로드맵

ERD는 V1 전체를 미리 설계하지만 구현과 migration은 Vertical Slice 단위로 진행한다.

| Slice | 목표 | 출시 가능한 결과 |
|---|---|---|
| 0. Foundation | Java/Spring/React/PostgreSQL/Flyway/Docker/CI bootstrap | 로컬·CI에서 health check 성공 |
| 1. Auth/Household | 로그인, 세션, 사용자 2명, Household 경계 | 인증 후 Household 진입 가능 |
| 2. Basic Ledger | Account, Category, 수입·지출, 빠른 입력, 목록 | 실제 가계부 최소 사용 가능 |
| 3. Transfer/Card | Account Entry, 이체, 신용카드, 카드대금 | 잔액·부채 계산 가능 |
| 4. Calendar | 월 달력, 일별 내역, 개인/공동 필터 | Weple형 메인 사용 흐름 완성 |
| 5. Budget | 전체·개인·공동·카테고리 예산 | 월 예산 관리 가능 |
| 6. Statistics | 기간·카테고리·주체·전월 비교 | 소비 분석 가능 |
| 7. Recurring | 월급·구독·적금 자동 생성 | 반복 입력 감소 |
| 8. Marriage Goal | Goal/Account 연결, 달성률·예상일 | 결혼자금 추적 가능 |
| 9. Assets | 자산·부채·순자산·월 추이 | 재무 상태 확인 가능 |
| 10. Production | PWA, CSV, backup, Mac mini 배포 | 실제 2인 운영 시작 |

## Release Gate

- `dev`는 검증된 Slice를 누적한다.
- `dev → main`은 의미 있는 사용자 흐름이 완료됐을 때만 진행한다.
- Production credential, 실제 DB migration, 배포는 별도 운영 Gate를 통과해야 한다.
- 재무 불변식 테스트가 실패하면 release할 수 없다.

## 출시 전 결정 항목

다음은 현재 구현을 막지 않으므로 해당 Slice에서 확정한다.

- 앱 이름의 최종 한글 브랜드명
- 대표 아이콘, 색상, 상세 디자인 토큰
- 실제 결혼자금 목표 금액과 목표일
- 운영 백업 보관기간과 외부 백업 위치
- 실제 도메인과 Cloudflare route
