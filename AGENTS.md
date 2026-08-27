# AGENTS.md

이 문서는 `our-ledger` 저장소에서 사람과 코드 에이전트가 따라야 하는 최상위 작업 계약이다.

## 1. 언어 규칙

- Issue 제목과 본문은 한글로 작성한다.
- Pull Request 제목과 본문은 한글로 작성한다.
- README, docs, ADR, 운영 문서는 한글로 작성한다.
- 커밋은 `type: 한글 요약` 형식을 권장한다. 예: `docs: 초기 도메인 문서 구성`.
- 코드 식별자, 패키지명, API 경로, DB 컬럼명, enum, 기술 고유명사는 영어를 유지한다.
- 번역으로 의미가 흐려지는 회계·개발 용어는 한글 설명 뒤 영어 식별자를 병기한다.

## 2. 우선순위

충돌 시 다음 순서로 따른다.

1. 보안과 데이터 무결성
2. 이 문서의 금지 사항
3. Accepted ADR
4. 도메인 및 데이터 계약 문서
5. Issue의 명시적 수용 기준
6. 기존 코드 관례

Issue가 문서 계약과 충돌하면 임의 구현하지 말고 `DECISION_REQUIRED`로 중단한다.

## 3. 작업 단위

- Issue 1개는 Pull Request 1개에 대응한다.
- Issue의 `IN` 범위만 구현한다.
- 편의상 발견한 인접 문제를 같은 Pull Request에 끼워 넣지 않는다.
- 별도 수정이 필요하면 새 Issue 후보로 기록한다.
- 기능, 리팩터링, 마이그레이션을 한 Pull Request에 무분별하게 혼합하지 않는다.

## 4. 브랜치와 merge

- 작업 시작 기준 브랜치는 기본적으로 `dev`다.
- 브랜치 예: `feature/issue-12-basic-ledger`, `fix/issue-31-refund-limit`.
- `main`과 `dev`에 직접 push하지 않는다.
- 에이전트는 merge, 배포, 태그 생성, release 발행을 수행하지 않는다.
- merge는 Hosted CI와 독립 리뷰가 완료된 뒤 사용자가 수행한다.

## 5. 필수 작업 순서

1. Issue 전체를 읽는다.
2. 이 문서를 읽는다.
3. Issue에 연결된 docs와 ADR을 읽는다.
4. 현재 코드, 테스트, migration, API 계약을 조사한다.
5. 최소 변경 계획을 세운다.
6. 구현한다.
7. 자동 테스트와 `./scripts/verify.sh`를 실행한다.
8. 관련 문서, ADR, API 계약, ERD를 동기화한다.
9. `git diff`를 자체 리뷰한다.
10. Pull Request를 생성하거나 갱신한다.
11. Hosted CI를 확인하고 실패 원인을 수정한다.
12. 모든 필수 검증이 통과하면 READY 상태에서 정지한다.

## 6. 재무 불변식

다음 규칙은 일반 구현 편의보다 우선한다.

- `TRANSFER`는 수입 또는 소비로 집계하지 않는다.
- 신용카드 사용 시 소비와 카드 부채가 증가한다.
- 카드대금 납부는 소비를 다시 증가시키지 않는다.
- `REFUND`는 원 거래 소비를 감소시키며 누적 환불액은 원 거래액을 초과할 수 없다.
- 삭제된 거래는 모든 잔액·예산·통계·목표 계산에서 제외한다.
- 다른 `Household`의 Member, Account, Category, Goal을 참조할 수 없다.
- 저축계좌 사이의 이동을 신규 저축으로 집계하지 않는다.
- Goal 금액을 거래와 별도로 입력해 자산을 이중 집계하지 않는다.
- 반복거래는 동일한 `(recurring_id, recurrence_date)`로 두 번 생성될 수 없다.
- 금액은 KRW 최소 화폐 단위의 양수 `BIGINT`로 저장하고 방향은 거래·entry 의미로 표현한다.

상세 기준은 `docs/07-quality/financial-invariants.md`를 따른다.

## 7. 데이터 변경 규칙

- Flyway migration은 이미 공유된 환경에 적용된 뒤 수정하지 않는다.
- 파괴적 migration은 별도 승인 없이 수행하지 않는다.
- 컬럼 삭제, 타입 축소, 데이터 재작성, 대량 backfill은 별도 Issue와 롤백 계획이 필요하다.
- 운영 데이터 migration, 실제 계정 생성, 실데이터 삭제는 수행하지 않는다.
- JPA schema auto-create/update를 운영 계약으로 사용하지 않는다.

## 8. 보안 금지 사항

- secret, 비밀번호, 토큰, 실제 계좌번호, 전체 카드번호를 커밋하지 않는다.
- `.env`, private key, keystore, 운영 DB dump를 커밋하지 않는다.
- 인증·인가 검증을 프론트엔드에만 의존하지 않는다.
- Household ID를 요청값 그대로 신뢰하지 않는다.
- 로그에 비밀번호, 세션 ID, CSRF token, 전체 금융 식별정보를 남기지 않는다.
- 사용자의 명시적 승인 없이 production deploy, Cloudflare 설정 변경, Tailscale ACL 변경을 수행하지 않는다.

## 9. 문서 동기화

다음 변경은 문서 수정 여부를 반드시 검토한다.

- 도메인 규칙 변경: `docs/02-domain/`
- 테이블·제약·인덱스 변경: `docs/03-data/`
- API 요청·응답·오류 변경: `docs/04-api/`
- 화면 흐름 변경: `docs/05-frontend/`
- 인증·권한 변경: `docs/06-security/`
- 테스트 계약 변경: `docs/07-quality/`
- 배포·백업 변경: `docs/08-operations/`
- 기존 결정을 뒤집는 변경: 신규 ADR 또는 기존 ADR supersede

문서 변경이 불필요하면 Pull Request에 이유를 적는다.

## 10. 완료 기준

- Issue 수용 기준을 모두 충족한다.
- 관련 테스트가 추가되거나 변경된다.
- `./scripts/verify.sh`가 통과한다.
- migration과 rollback 위험이 검토됐다.
- 재무 불변식 회귀 테스트가 통과한다.
- 관련 문서가 동기화됐다.
- 미실행 검증과 남은 위험을 Pull Request에 명시했다.
- Hosted CI 필수 check가 성공했다.

## 11. 중단 조건

다음 상황에서는 추측으로 진행하지 않고 `DECISION_REQUIRED`를 남긴다.

- 제품 범위 또는 사용자 경험 선택이 필요함
- Accepted ADR을 변경해야 함
- 재무 계산 계약이 불명확함
- 개인정보 공개 범위가 달라짐
- 파괴적 데이터 변경이 필요함
- 보안 정책 또는 운영 권한 변경이 필요함
- Issue 범위를 실질적으로 확대해야 함

`DECISION_REQUIRED`에는 현재 상태, 막힌 이유, 선택지, 각 선택지의 영향, 권장안을 포함한다.
