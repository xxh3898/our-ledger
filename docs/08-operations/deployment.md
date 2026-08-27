---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - AGENTS.md
  - 08-operations/backup-restore.md
---

# 배포 구조

## 목표 구조

```text
사용자 브라우저/PWA
→ Cloudflare
→ Cloudflare Tunnel
→ Mac mini Nginx
→ frontend 정적 파일 / Spring Boot API
→ PostgreSQL
```

관리 접근은 Tailscale을 사용한다. 공유기에서 애플리케이션 또는 DB 포트를 직접 개방하지 않는다.

## Container

예상 서비스:

- `web`: Nginx 또는 frontend serving
- `api`: Spring Boot Java 25
- `db`: PostgreSQL 18
- `backup`: pg_dump 실행 도구 또는 host scheduler
- `cloudflared`: 기존 운영 방식에 따라 별도 또는 공용 tunnel

## 환경 분리

- local
- test/CI
- production

production secret은 저장소에 두지 않는다. `.env.example`에는 이름과 설명만 둔다.

## Health

- API liveness/readiness
- PostgreSQL 연결 확인
- frontend 정적 파일 응답
- Compose healthcheck

readiness가 통과하기 전 신규 container로 traffic을 전환하지 않는다.

## 배포 Gate

에이전트는 production deploy를 수행하지 않는다. 사용자가 다음을 확인한 뒤 명시적으로 실행한다.

- image/tag 또는 commit SHA
- migration 영향
- backup 최신성
- rollback 절차
- Cloudflare route
- health check

## 롤백

애플리케이션 image 롤백과 DB rollback을 구분한다. forward-only migration으로 인해 이전 image가 새 schema와 호환되지 않으면 단순 image 롤백을 금지한다.
