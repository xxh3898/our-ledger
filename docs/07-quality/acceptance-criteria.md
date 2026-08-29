---
status: active
version: 0.6
last_updated: 2026-08-29
related:
  - 00-overview/roadmap.md
  - ADR-008
  - 08-operations/backup-restore.md
---

# V1 인수 기준

## 기능

- Cloudflare Access에서 허용된 두 사용자가 각자 인증되고 같은 Household 데이터를 본다.
- 검증된 Access identity가 내부 활성 User에 매핑되지 않으면 접근이 거부된다.
- 수입·지출·이체를 생성·수정·삭제할 수 있다.
- 치호 개인, 여자친구 개인, 공동 필터가 달력·목록·통계에서 일관된다.
- 카드 지출과 카드대금 납부가 중복 소비로 잡히지 않는다.
- 전체·부분 환불이 원 거래와 연결되고 실제 PostgreSQL 동시 요청에서도 초과 환불이 차단된다.
- 환불은 원 거래의 금융 bucket과 Account Entry 효과를 반대로 상속하고, 삭제 시 잔액·순소비·예산이 복원된다.
- active Refund가 있는 원 거래의 금융 edit/delete는 차단되고 환불 자체는 삭제 후 재생성한다.
- 월 예산 사용액이 거래와 일치한다.
- 반복 거래가 Household timezone과 DAILY/WEEKLY/MONTHLY/YEARLY schedule에 따라 canonical Transaction으로 중복 없이 생성된다.
- 월말·윤년 clamp, 지연 실행 catch-up, 동시 worker에서도 최초 anchor와 발생일별 멱등성이 보존된다.
- 설정에서 반복 규칙을 생성·수정·일시정지·재개할 수 있고 재개 시 일시정지 기간을 소급 생성하지 않는다.
- 자동 생성 거래가 달력·예산·통계·저축 활동에 일반 원장과 같은 값으로 반영되고 `반복` provenance가 표시된다.
- 결혼자금 현재 금액이 연결 Account와 일치한다.
- 결혼자금 Goal 생성·수정과 eligible Account 연결·해제가 current Household 경계에서 동작한다.
- 결혼자금 이번 달/6개월/완료 3개월 평균과 예상 상태가 Goal 경계 TRANSFER와 linked_at 기준에 일치한다.
- Goal 내부 이동, 연결 전 거래, INCOME/EXPENSE/REFUND를 신규 Goal 저축으로 중복 집계하지 않는다.
- concurrent Goal 생성·Account 연결·snapshot posting·target PATCH가 PostgreSQL 제약과 lock/version 계약을 지킨다.
- Home과 Goal 상세가 실제 read model 또는 정상 empty/error 상태를 표시하고 수동 Goal 기여금 action을 제공하지 않는다.
- Assets의 현재 Account 잔액, 총자산·총부채·순자산이 opening balance와 유효 Entry에서 파생되고 active·archived, 양수·0·음수를 그대로 포함한다.
- Assets의 actual Member PERSONAL/SHARED 소계는 Account ownership으로 귀속되고 합이 Household와 일치하며 다른 Household data를 포함하지 않는다.
- Assets가 Household timezone 직전 11개 완료 월말과 현재 한 점을 반환하고 opening date, logical delete, generated recurring 거래를 같은 원장 의미로 처리한다.
- Assets 화면이 canonical all/Member/shared URL, accessible 추이 표, loading/error/empty, Account Settings와 Quick Entry 경로를 제공한다.
- Settings에서 Household timezone 현재 월 기본 범위 또는 지정 기간의 current Household 거래 CSV를 내려받을 수 있다.
- CSV는 미삭제 Transaction당 한 row, 19개 한국어 고정 column, UTF-8 BOM, RFC 4180, 안정 정렬을 지킨다.
- REFUND/Recurring provenance와 archived reference를 유지하고 canonical Entry 손상은 fail-closed한다.
- 사용자/reference text의 formula prefix를 방어하며 foreign Household, `lastFour`, email, credential을 포함하지 않는다.
- PWA를 모바일 홈 화면에 설치할 수 있다.

## 품질

- 모든 재무 불변식 테스트 통과
- 다른 Household 접근 테스트 통과
- Access JWT 서명·issuer·audience·만료 검증 테스트 통과
- production profile에서 개발용 identity 우회가 비활성임을 검증
- Flyway clean database 적용 통과
- backend/frontend build와 lint/test 통과
- 핵심 모바일 E2E 통과
- API 응답과 로그에 secret·Access JWT·Access cookie·stack trace 없음

## 운영

- Mac mini Docker Compose 배포 성공
- 외부 공개 경로는 Cloudflare Access + Cloudflare Tunnel 사용
- Cloudflare Access Allow 정책이 실제 사용자 두 이메일로 제한됨
- `cloudflared` Access JWT 검증이 활성화됨
- Access를 우회해 origin에 접근 가능한 공용 경로가 없음
- DB 포트 직접 공개 없음
- 자동 backup 성공 확인
- 별도 환경에서 restore drill 1회 성공
- health check와 uptime monitor 확인

## 문서

- API, ERD, 인증, 인가, 운영 문서가 실제 구현과 일치
- production 환경 변수 목록과 secret 주입 방식 기록
- 미결정 운영 정책이 production gate 전에 해소
