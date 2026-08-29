# our-ledger

개인 소비, 공동 소비, 예산, 자산, 저축 목표를 한 공간에서 관리하는 **2인용 재무관리 PWA**다.

`our-ledger`는 서로 정산하기 위한 앱이 아니다. 두 사람이 각자의 돈과 함께 쓰는 돈을 투명하게 기록하고, 결혼자금을 포함한 공동 목표를 향해 실제 현금흐름을 관리하는 것이 목적이다.

## 현재 상태

- 단계: Slice 10C-2A — Backup/Restore Safety Gate
- 구현 코드: Auth/Household부터 CSV Export까지의 제품 흐름, immutable production runtime, 검증된 PostgreSQL custom backup과 disposable restore drill
- 로컬 실행: 개발 전용 Docker Compose 또는 Java 25 / Node.js 24
- 기본 브랜치 전략: `feature/* → dev → main`
- 문서, Issue, Pull Request, 사람이 읽는 설명: 한글
- 코드 식별자, API 경로, DB 컬럼, enum, 기술 고유명사: 영어

## 제품 핵심

1. 입력은 빠르게 한다.
2. 기록한 데이터는 자유롭게 필터링하고 분석할 수 있어야 한다.
3. 개인 소비와 공동 소비를 항상 구분할 수 있어야 한다.
4. 수입·소비·저축·자산 계산은 거래 원장에서 파생한다.
5. 동일한 돈을 목표와 거래에 중복 입력하지 않는다.
6. 기능이 많아도 평소 화면은 단순하게 유지한다.

## V1 주요 기능

- 수입, 지출, 이체
- 치호 개인, 여자친구 개인, 공동 소비 구분
- 계좌, 현금, 적금, 신용카드 관리
- 달력 중심 거래 조회와 조합 필터
- 카테고리 그룹 및 사용자 커스텀
- 월 예산과 카테고리 예산
- 반복 거래
- 환불과 부분 환불
- 통계, 전월 비교, 자산·부채·순자산
- 결혼자금 목표와 예상 달성 시점
- CSV 내보내기
- PWA 설치

현재 CSV 내보내기는 Settings에서 Household timezone 기간을 지정해 실행한다. `GET /api/v1/exports/transactions.csv`는 미삭제 Transaction을 canonical Entry와 함께 검증하고 한국어 19개 column, UTF-8 BOM, RFC 4180, spreadsheet formula 방어를 적용한다. CSV는 운영 backup의 대체물이 아니다.

Slice 10C-1은 Java 25 API와 Node 24 build 결과를 non-root runtime image로 분리하고 Nginx가 정적 SPA와 `/api/**`를 same-origin으로 제공하는 production origin harness를 추가했다. Slice 10C-2A는 existing healthy PostgreSQL의 online custom dump를 owner-only atomic bundle과 checksum/metadata로 검증하는 one-shot command, 합성 non-empty DB를 별도 volume에 실제 복구하는 drill을 추가한다.

이 source gate는 실제 production backup을 실행하거나 schedule·retention·외부복제·production restore를 활성화하지 않는다. Cloudflare/Tunnel, production secret/User/DB, observability/alert와 deploy도 별도 승인 대상이다. Slice 10B PWA는 최종 한글 앱 이름과 production icon 확정 전까지 보류한다.

## 기술 기준

| 영역 | 기준 |
|---|---|
| Backend | Java 25, Spring Boot 4.1.1, Gradle Wrapper |
| Database | PostgreSQL 18.6, Flyway, Spring Data JPA |
| Frontend | React 19.2, TypeScript 6.0, Vite 8.x |
| Runtime | Node.js 24 LTS |
| 인증 | Cloudflare Access, Access JWT 검증, Spring Security 내부 인가 |
| 테스트 | JUnit, Testcontainers, Frontend 단위·컴포넌트·E2E 테스트 |
| 배포 | Docker Compose, Mac mini, Nginx, Cloudflare Tunnel |
| 운영 접근 | Tailscale 기반 관리 접근 |

세부 패치 버전은 프로젝트 bootstrap PR에서 lockfile과 wrapper로 고정한다. Spring 생태계 하위 의존성은 가능한 한 Spring Boot dependency management에 위임한다.

현재 bootstrap은 Spring Boot `4.1.1`, Gradle `9.7.1`, React `19.2.8`, TypeScript `6.0.3`, Vite `8.2.2`, Node.js `24.20.0`을 project file에 고정한다. PostgreSQL 개발·테스트 image는 `18.6`을 사용한다.

production 접근은 Cloudflare Access에서 허용된 두 사용자만 통과시키고, `cloudflared`와 Spring Security가 Access JWT를 검증한다. 애플리케이션 자체 사용자 비밀번호는 저장하지 않는다. 세부 계약은 [`ADR-008`](docs/09-decisions/ADR-008-cloudflare-access-authentication.md)과 [`docs/06-security/authentication.md`](docs/06-security/authentication.md)를 따른다.

Backend는 `Cf-Access-Jwt-Assertion`의 RS256 서명, issuer, audience, 시간, email claim을 검증한 뒤 ACTIVE 내부 User와 정확히 하나의 Household membership을 요구한다. Cloudflare 설정이 없는 default/production 실행은 fail-closed로 시작에 실패한다. 실제 값은 저장소 밖에서 다음 환경변수로 주입한다.

- `CLOUDFLARE_ACCESS_ISSUER`
- `CLOUDFLARE_ACCESS_JWK_SET_URI`
- `CLOUDFLARE_ACCESS_AUDIENCE`

## Transfer/Card Ledger 범위

Slice 3는 Basic Ledger에 Account Entry 기반 이체, 신용카드 지출과 카드대금 납부를 추가한다.

- `GET/POST/PATCH /api/v1/accounts`
- `GET/POST/PATCH /api/v1/category-groups`
- `GET/POST/PATCH /api/v1/categories`
- `GET/POST/PATCH/DELETE /api/v1/transactions`
- 수입·일반 지출·카드 지출은 `PRIMARY` Entry 1개, 이체는 `SOURCE`와 `DESTINATION` Entry 각 1개
- ASSET 지출 `-amount`, CREDIT_CARD/LIABILITY 지출 `+amount`, ASSET→LIABILITY 카드대금 납부는 양쪽 `-amount`
- Account 현재 잔액 = 기초 잔액 + 미삭제 Transaction Entry 합
- Account/Category/Group은 물리삭제 대신 archive, Transaction은 optimistic version을 요구하는 논리삭제
- 다른 Household의 Member/Account/Category/Transaction은 모두 현재 Household 조건으로 차단

LIABILITY source 이체와 REFUND는 후속 Slice이며 현재 API가 stable `422` error code로 거부한다. 기본 Category seed는 자동 생성하지 않는다.

## 저장소 구조

```text
our-ledger/
├─ AGENTS.md
├─ README.md
├─ backend/             # Spring Boot API, Flyway, Gradle Wrapper
├─ frontend/            # React/TypeScript/Vite, npm lockfile
├─ infra/               # immutable image와 non-root Nginx production 자산
├─ docs/                # 제품·domain·data·quality 계약
├─ scripts/             # local/CI 검증 진입점
├─ compose.dev.yaml     # local 개발 전용
├─ compose.prod.yaml    # image 기반 production origin harness
├─ compose.verify.yaml  # host runtime이 없을 때의 격리 검증
└─ .github/
```

상세 문서 색인은 [`docs/README.md`](docs/README.md)를 따른다.

## 개발 흐름

```text
Issue 설계
→ feature branch
→ 구현·테스트·문서 동기화
→ Pull Request
→ Hosted CI
→ 독립 리뷰
→ 사용자가 merge
```

기본 원칙은 **Issue 1개 = Pull Request 1개**다. `main`과 `dev`에 직접 push하거나 에이전트가 직접 merge하지 않는다.

## 로컬 실행

개발용 PostgreSQL만 실행하려면 sample을 복사하고 placeholder password를 로컬 값으로 바꾼다. `.env.dev.local`은 Git에서 제외된다.

```bash
cp .env.example .env.dev.local
docker compose --env-file .env.dev.local -f compose.dev.yaml up -d --wait postgres
```

Java/Node를 host에 설치하지 않고 전체 애플리케이션을 실행하려면 개발 profile을 사용한다. API와 frontend port는 loopback에만 bind된다.

최초 local data가 필요하면 `.env.dev.local`의 가짜 `example.test` 값을 확인하고 `OUR_LEDGER_BOOTSTRAP_ENABLED=true`로 한 번 시작한다. 두 User와 한 Household가 생성된 뒤 다음 startup부터 다시 `false`로 둔다. 정확히 같은 입력의 재실행은 no-op이고, 부분 생성·다른 표시명·다른 membership은 덮어쓰지 않고 startup을 실패시킨다. 실제 이메일이나 production DB에는 이 절차를 실행하지 않는다.

```bash
docker compose --env-file .env.dev.local -f compose.dev.yaml --profile app up
```

- Frontend: `http://127.0.0.1:5173`
- Backend health: `http://127.0.0.1:8080/actuator/health`
- PostgreSQL: `127.0.0.1:${POSTGRES_PORT}`

Vite development proxy는 `.env.dev.local`의 `OUR_LEDGER_LOCAL_IDENTITY_EMAIL`을 `X-Our-Ledger-Local-Identity`로 backend에 전달한다. 이 header filter는 `local`/`test` profile에만 존재하고 내부 User와 Household membership 검증을 그대로 거친다.

종료할 때는 개발 data와 dependency cache를 보존하는 일반 `down`을 사용한다.

```bash
docker compose --env-file .env.dev.local -f compose.dev.yaml --profile app down
```

## 로컬 검증

```bash
./scripts/verify.sh
```

이 명령은 repository/docs/Flyway/Compose 검사, Backend unit·PostgreSQL integration·health/REST Docs test, Frontend lint·typecheck·component test·production build, disposable backup/restore drill과 production runtime smoke를 순서대로 실행한다.

host에 Java 25 또는 Node.js 24가 없으면 `compose.verify.yaml`의 격리 container를 사용한다. 이 fallback은 운영 resource나 Docker socket을 참조하지 않으며 검증 PostgreSQL data는 container 종료와 함께 사라지고 dependency cache volume은 보존된다. production runtime smoke는 매번 고유 Compose project와 임시 loopback port, 합성 credential, disposable PostgreSQL volume을 사용하고 성공·실패 모두에서 container/network/volume과 검증 image tag를 제거한다. Hosted Backend CI는 기본 Testcontainers 경로를 사용한다.

production harness의 image build, 환경변수, render/start/inspect/stop/rollback과 backup one-shot 계약은 [`infra/README.md`](infra/README.md)를 따른다. 문서의 명령은 운영 실행 승인, 실제 backup/restore 또는 deploy 완료를 의미하지 않는다.

## 범위 밖

V1에서는 은행·카드 자동 연동, 영수증 OCR, AI 소비 분석, 투자자산 시세, 네이티브 앱, 오프라인 쓰기 동기화를 구현하지 않는다.
