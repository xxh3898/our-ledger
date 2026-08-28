---
status: active
version: 0.7
last_updated: 2026-08-28
related:
  - 01-product/feature-matrix.md
  - 07-quality/acceptance-criteria.md
  - ADR-008
---

# 개발 로드맵

ERD는 V1 전체를 미리 설계하지만 구현과 migration은 Vertical Slice 단위로 진행한다.

| Slice | 목표 | 출시 가능한 결과 |
|---|---|---|
| 0. Foundation | Java/Spring/React/PostgreSQL/Flyway/Docker/CI bootstrap | 로컬·CI에서 health check 성공 |
| 1. Auth/Household | Cloudflare Access identity 검증, 내부 User 매핑, 사용자 2명, Household 경계 | Access 인증 후 내부 User/Household 진입 가능 |
| 2. Basic Ledger | Account, Category, 수입·지출, 빠른 입력, 목록 | 실제 가계부 최소 사용 가능 |
| 3. Transfer/Card | Account Entry, 이체, 신용카드, 카드대금 | 잔액·부채 계산 가능 |
| 4. Calendar | 월 달력, 일별 내역, 개인/공동 필터 | Weple형 메인 사용 흐름 완성 |
| 5. Budget | 전체·개인·공동·카테고리 예산 | 월 예산 관리 가능 |
| Pre-6 Refund Gate | 전체·부분 환불, 누적 상한, 원 거래 lineage 보호 | Statistics가 신뢰할 환불 원장 완성 |
| 6. Statistics | 기간·카테고리·주체·전월 비교 | 소비 분석 가능 |
| 7. Recurring | 월급·구독·적금 자동 생성 | 반복 입력 감소 |
| 8. Marriage Goal | Goal/Account 연결, 달성률·예상일 | 결혼자금 추적 가능 |
| 9. Assets | 자산·부채·순자산·월 추이 | 재무 상태 확인 가능 |
| 10. Production | PWA, CSV, backup, Cloudflare Access/Tunnel, Mac mini 배포 | 허용된 두 사용자의 실제 운영 시작 |

## Slice 3 구현 경계

Transfer/Card는 Basic Ledger의 Account·Category 수동 설정과 INCOME/EXPENSE에 ASSET→ASSET 이체, CREDIT_CARD/LIABILITY 지출, ASSET→LIABILITY 카드대금 납부를 추가한다. 거래 수정은 지원 유형 사이에서 expected Entry set을 완전히 재구성한다.

LIABILITY source 이체, REFUND, 카드 명세·결제일·한도·할부, Category seed, Calendar/Statistics aggregation과 최종 Home 디자인은 Slice 3 완료 조건이 아니다.

## Slice 5 구현 경계

Budget은 Household timezone 월 단위로 HOUSEHOLD, 실제 Member별 PERSONAL, SHARED와 선택 EXPENSE Category의 예산을 저장한다. 사용액은 Transaction의 `NORMAL EXPENSE - REFUND EXPENSE`에서 매번 파생하며 미설정과 0원, 초과 상태를 구분한다.

Slice 5는 Budget CRUD, optimistic locking, 기본 Scope 카드, 사용자 설정 Category Budget, 월 이동과 기존 Transaction 목록을 재사용한 drill-down까지 포함한다. 자동 이월·전월 자동 복사, 거래 저장 차단, REFUND 생성, Statistics·Recurring·Goal·Assets 구현은 포함하지 않는다.

## Pre-Statistics Refund Correctness Gate

Slice 6에 들어가기 전에 ADR-004의 REFUND Transaction을 실제 write path로 활성화한다. 원 NORMAL EXPENSE 하위 resource에서 전체·부분 환불을 생성하고, 원 거래의 Scope/Owner/Payer/Category/PRIMARY Account와 Entry 방향을 상속한다.

원 거래 row lock 뒤 active refund 합계를 계산해 동시 요청에서도 누적 환불액이 원 금액을 초과하지 않게 한다. active Refund가 있는 원 거래의 금융 edit/delete는 차단하고 Refund는 logical delete 후 필요하면 재생성한다. Calendar, Budget, Account 잔액은 active Refund 생성·삭제를 같은 원장 의미로 즉시 반영한다.

이 Gate는 Slice 번호를 재정의하지 않으며 Statistics, Recurring, Goal, Assets, production 작업을 포함하지 않는다. 기존 V1~V6 schema가 계약을 지원하므로 migration을 추가하지 않는다.

## Slice 6 구현 경계

Statistics는 current Household의 유효 Transaction, Account Entry, Account 속성에서 기간·주체별 수입, 순소비, 저축, 저축률과 주체·Category·Account·월 breakdown을 매번 파생한다. current/comparison 범위는 Household timezone의 포함 날짜이며 비율은 소수점 한 자리 `HALF_UP`, 분모가 0이면 `null`이다.

수입·순소비·Category·Account·주체 drill-down은 기존 Transaction 목록을 재사용하고, 저축은 impact 0인 Transfer를 제외하는 전용 read endpoint를 사용한다. 저축은 Transfer에 Scope가 없으므로 ALL에서만 제공하며 개인·공동 view에 Account ownership으로 귀속하지 않는다.

Slice 6은 Statistics read model/API, 기간·주체 URL state, 월별 표와 drill-down을 포함한다. 통계 persistence/cache/materialized view/Redis, 근거 없는 index, Recurring·Goal·Assets·CSV·PWA·production 작업은 포함하지 않으며 schema migration을 추가하지 않는다.

## Slice 7 Recurring 구현 경계

Recurring은 Household timezone의 `start_date` anchor와 `scheduled_local_time`을 가진 rule을 저장하고 due occurrence마다 기존 canonical posting 로직으로 일반 Transaction과 Account Entry를 생성한다. rule 자체는 잔액·Calendar·Budget·Statistics에 포함하지 않는다.

V7은 rule/template Account table, generated lineage와 full occurrence unique, operational cursor를 additive로 추가한다. backend minute poll은 occurrence별 새 transaction에서 rule row lock과 due 재확인, generated 원장 저장, cursor advance를 원자 처리하고 bounded catch-up과 one-rule failure isolation을 제공한다.

Settings Sheet는 active/paused/ended 목록, 생성·수정·중지·재개를 제공한다. pause 기간은 resume 시 소급 생성하지 않고 generated history는 rule edit와 독립적인 snapshot으로 유지한다. recurring REFUND, `auto_post=false`, LIABILITY source, 예정 거래 승인, 알림, 별도 하단 tab, production 작업은 포함하지 않는다.

## Release Gate

- `dev`는 검증된 Slice를 누적한다.
- `dev → main`은 의미 있는 사용자 흐름이 완료됐을 때만 진행한다.
- Production credential, 실제 DB migration, Cloudflare Access/Tunnel 설정, 배포는 별도 운영 Gate를 통과해야 한다.
- 재무 불변식 테스트가 실패하면 release할 수 없다.
- production에서 Access JWT 검증 우회 경로가 존재하면 release할 수 없다.

## 출시 전 결정 항목

다음은 현재 구현을 막지 않으므로 해당 Slice에서 확정한다.

- 앱 이름의 최종 한글 브랜드명
- 대표 아이콘, 색상, 상세 디자인 토큰
- 실제 결혼자금 목표 금액과 목표일
- 운영 백업 보관기간과 외부 백업 위치
- 실제 도메인과 Cloudflare route
- Cloudflare Access session duration
- 내부 User bootstrap/provision 운영 절차
