---
status: superseded
version: 0.2
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
  - ADR-008-cloudflare-access-authentication.md
---

# ADR-007: 서버 세션 기반 인증

## Status

Superseded by [ADR-008](ADR-008-cloudflare-access-authentication.md)

## Context

단일 same-origin PWA와 Spring API, 사용자 2명 구조에서 JWT는 token rotation, 저장, 폐기 복잡도를 늘린다고 판단해 애플리케이션 자체 비밀번호와 Spring Security 서버 세션을 사용하기로 했다.

## Decision

Spring Security 서버 세션과 Secure/HttpOnly Cookie를 사용한다. 상태 변경 요청은 CSRF 보호를 적용한다.

## Consequences

- 단순한 애플리케이션 로그인·로그아웃과 강제 session 폐기
- 브라우저 보안 기능 활용
- 서버 session 저장과 비밀번호·cookie 정책 관리 필요

## Rejected Alternatives

### Access/Refresh JWT

현재 제품 규모와 배포 형태에서 추가 복잡도의 이득이 없어 거절했다.

## Superseded 이유

배포 경계가 Cloudflare Tunnel로 확정되고 실제 사용자가 두 명으로 제한되면서, 애플리케이션이 비밀번호 인증을 직접 운영하는 것보다 Cloudflare Access에서 외부 인증과 접근 허용을 처리하는 편이 공격 표면과 운영 부담을 줄일 수 있다고 재평가했다.

새 인증 계약은 ADR-008을 따른다. 이 문서는 과거 결정 기록을 보존하기 위해 삭제하지 않는다.
