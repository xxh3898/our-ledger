# our-ledger

개인 소비, 공동 소비, 예산, 자산, 저축 목표를 한 공간에서 관리하는 **2인용 재무관리 PWA**다.

`our-ledger`는 서로 정산하기 위한 앱이 아니다. 두 사람이 각자의 돈과 함께 쓰는 돈을 투명하게 기록하고, 결혼자금을 포함한 공동 목표를 향해 실제 현금흐름을 관리하는 것이 목적이다.

## 현재 상태

- 단계: 제품·도메인 설계 및 프로젝트 하네스 초기화
- 구현 코드: 아직 없음
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

production 접근은 Cloudflare Access에서 허용된 두 사용자만 통과시키고, `cloudflared`와 Spring Security가 Access JWT를 검증한다. 애플리케이션 자체 사용자 비밀번호는 저장하지 않는다. 세부 계약은 [`ADR-008`](docs/09-decisions/ADR-008-cloudflare-access-authentication.md)과 [`docs/06-security/authentication.md`](docs/06-security/authentication.md)를 따른다.

## 저장소 구조

```text
our-ledger/
├─ AGENTS.md
├─ README.md
├─ backend/
├─ frontend/
├─ infra/
├─ docs/
├─ scripts/
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

## 로컬 검증

```bash
./scripts/verify.sh
```

구현 전인 backend/frontend는 자동으로 건너뛴다. 해당 영역에 빌드 파일이 생긴 뒤에는 검증 도구 누락을 실패로 처리한다.

## 범위 밖

V1에서는 은행·카드 자동 연동, 영수증 OCR, AI 소비 분석, 투자자산 시세, 네이티브 앱, 오프라인 쓰기 동기화를 구현하지 않는다.
