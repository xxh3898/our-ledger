---
status: active
version: 0.4
last_updated: 2026-08-29
related:
  - 06-security/privacy-model.md
  - ADR-008
---

# 관측성

## 현재 상태

Slice 10C-1은 container healthcheck와 stdout/stderr log 경계를 제공한다. Slice 10C-2A는 verified backup 뒤에만 atomically 갱신되는 비민감 `last-success.json`과 명확한 process exit status를 제공한다. Uptime Kuma 연결, metrics exporter/dashboard, backup freshness·scheduler alert, 실제 임계치와 알림 채널은 Slice 10C-2B/10D 범위이며 아직 활성화하지 않았다.

## Backup freshness interface

`last-success.json`에는 latest verified bundle의 UTC timestamp, Flyway schema version, byte size, SHA-256, artifact 이름과 PostgreSQL client/server version만 있다. dump 내용, email, memo, DB password, token/cookie와 absolute production path는 포함하지 않는다.

monitor는 dump를 열거나 backup command를 재실행하지 않고 marker freshness와 one-shot exit status만 읽어야 한다. stale threshold, alert channel, disk threshold와 실제 scheduler는 10C-2B/10D에서 결정한다. failed backup은 이전 marker를 현재 성공 시각으로 갱신하지 않는다.

## 목표

사용자 2명 서비스에 과도한 플랫폼을 도입하지 않고 장애 발견과 원인 확인에 필요한 최소 관측성을 갖춘다.

## Health와 Uptime

- API readiness endpoint
- frontend URL
- Cloudflare 외부 경로
- PostgreSQL container health
- Uptime Kuma 등 기존 홈서버 도구 활용

현재 public Nginx `/healthz`는 Nginx process/static 응답만 나타내며 API/DB detail을 노출하지 않는다. API readiness와 PostgreSQL health는 internal Compose dependency와 disposable smoke에서 확인한다. production 외부 monitor가 actuator를 직접 우회 호출하지 않게 한다.

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
