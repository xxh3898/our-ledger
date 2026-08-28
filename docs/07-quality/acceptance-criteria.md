---
status: active
version: 0.3
last_updated: 2026-08-28
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
- 반복 거래가 중복 없이 생성된다.
- 결혼자금 현재 금액이 연결 Account와 일치한다.
- CSV로 지정 기간 데이터를 내보낼 수 있다.
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
