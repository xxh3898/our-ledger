---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - 06-security/privacy-model.md
  - ADR-008
---

# 관측성

## 목표

사용자 2명 서비스에 과도한 플랫폼을 도입하지 않고 장애 발견과 원인 확인에 필요한 최소 관측성을 갖춘다.

## Health와 Uptime

- API readiness endpoint
- frontend URL
- Cloudflare 외부 경로
- PostgreSQL container health
- Uptime Kuma 등 기존 홈서버 도구 활용

## 로그

구조화된 application log를 사용한다.

필수 정보:

- timestamp
- level
- service/version
- traceId 또는 requestId
- error code
- endpoint와 status

금지 정보:

- password
- `Cf-Access-Jwt-Assertion`
- `CF_Authorization` 및 기타 cookie
- OTP와 CSRF credential
- 전체 request body
- 전체 계좌·카드 식별정보

## Metrics

초기 필수:

- 요청 수와 오류율
- 응답시간
- JVM memory/GC
- DB connection pool
- container restart
- disk 사용량
- backup 성공/실패

재무 Category나 memo 같은 사용자 행동 데이터를 외부 분석 서비스로 보내지 않는다.

## Alert

- 외부 health 연속 실패
- DB unhealthy
- disk 임계치
- backup 실패
- 반복거래 scheduler 연속 실패

알림 채널과 임계치는 production gate에서 기존 HomeOps 운영 방식에 맞춰 확정한다.
