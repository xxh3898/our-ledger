---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 09-decisions/README.md
---

# ADR-007: 서버 세션 기반 인증

## Status

Accepted

## Context

단일 same-origin PWA와 Spring API, 사용자 2명 구조에서 JWT는 token rotation, 저장, 폐기 복잡도를 늘린다.

## Decision

Spring Security 서버 세션과 Secure/HttpOnly Cookie를 사용한다. 상태 변경 요청은 CSRF 보호를 적용한다.

## Consequences

- 단순한 로그인·로그아웃과 강제 session 폐기
- 브라우저 보안 기능 활용
- 서버 session 저장과 cookie 정책 관리 필요

## Rejected Alternatives

### Access/Refresh JWT

현재 제품 규모와 배포 형태에서 추가 복잡도의 이득이 없어 거절한다.
