---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - ADR-007-session-authentication.md
  - 06-security/authentication.md
  - 06-security/authorization.md
  - 08-operations/deployment.md
---

# ADR-008: Cloudflare Access 기반 인증

## Status

Accepted

Supersedes [ADR-007](ADR-007-session-authentication.md).

## Context

`our-ledger`는 두 명만 사용하는 개인 재무관리 PWA이며 production origin은 Cloudflare Tunnel 뒤에 배치한다. 애플리케이션 자체 비밀번호 인증을 운영하면 password hash 저장, 초기 계정 발급, 비밀번호 변경·복구, brute-force 방어, 계정 잠금과 같은 별도 인증 운영 부담이 생긴다.

두 사용자 모두 인터넷에서 PWA에 접근해야 하지만, 애플리케이션 자체는 공개 회원가입 서비스가 아니다. 따라서 인터넷 경계에서 허용된 두 사용자만 통과시키고 Spring 애플리케이션은 검증된 외부 identity를 내부 User 및 Household 권한으로 연결하는 구조가 적합하다.

## Decision

V1 production 인증 경계로 Cloudflare Access를 사용한다.

### 접근 허용

- Cloudflare Access Self-hosted Application을 사용한다.
- Allow 정책에는 실제 사용자 두 명의 이메일만 명시적으로 등록한다.
- 인증 방식은 Cloudflare Access가 제공하는 One-time PIN 또는 별도로 연결한 IdP를 사용할 수 있다.
- `Login Methods: One-time PIN`만 Include하여 모든 유효 이메일을 허용하는 정책은 금지한다.
- 실제 허용 이메일은 저장소 문서나 코드에 커밋하지 않는다.

### Origin identity 검증

Cloudflare Access가 origin으로 전달하는 `Cf-Access-Jwt-Assertion`을 인증 근거로 사용한다.

production에서는 두 계층에서 검증한다.

1. `cloudflared`의 Access 검증을 활성화해 유효한 Access JWT가 없는 요청을 origin에 프록시하지 않는다.
2. Spring Security에서도 Access JWT의 서명과 `iss`, `aud`, 만료시간을 검증한 뒤 검증된 email claim을 내부 User에 매핑한다.

일반 요청 헤더나 클라이언트가 임의로 제공할 수 있는 이메일 헤더만으로 사용자를 인증하지 않는다.

### 내부 User 매핑

- `users.email`은 Cloudflare Access identity와 내부 User를 연결하는 정규화 식별자다.
- Access 인증 성공만으로 User를 자동 생성하지 않는다.
- V1의 두 User는 별도 bootstrap/provision 절차로 미리 생성한다.
- 유효한 Access JWT의 email이 내부 활성 User와 일치하지 않으면 접근을 거부한다.
- 내부 User가 Household의 활성 Member인지 별도로 확인한다.

### 애플리케이션 인증정보

V1에서는 애플리케이션 자체 로그인 비밀번호와 `password_hash`를 저장하지 않는다. 애플리케이션 자체 Access/Refresh JWT도 발급하지 않는다.

Cloudflare Access session과 애플리케이션의 재무 인가는 별도 책임이다. Access는 사용자의 외부 identity와 애플리케이션 진입 여부를 결정하고, Spring Security와 Service Layer는 내부 User 상태와 Household 리소스 권한을 결정한다.

### CSRF와 same-origin

Cloudflare Access를 사용하더라도 브라우저 기반 state-changing 요청 보호를 제거하지 않는다. same-origin PWA/API 구조를 유지하고, Spring Security 구현 단계에서 CSRF 또는 동등한 Origin 기반 요청 위조 방어를 적용한다. 구체적인 token repository와 frontend 전달 방식은 Auth/Household Slice에서 테스트와 함께 확정한다.

### 개발·테스트 환경

local/CI는 Cloudflare Access에 의존하지 않고 테스트 가능한 인증 어댑터를 사용할 수 있다. 단, production profile에서는 Access JWT 검증을 우회하는 개발용 identity 주입 기능이 활성화될 수 없다.

## Consequences

### 장점

- 애플리케이션이 사용자 비밀번호를 저장·복구·잠금 처리하지 않는다.
- 허용되지 않은 사용자는 애플리케이션 로그인 화면이나 API까지 도달하기 전에 차단할 수 있다.
- Cloudflare Tunnel 배포 구조와 인증 경계를 일치시킨다.
- Spring은 Household 및 도메인 인가에 집중할 수 있다.
- 사용자 두 명이라는 제품 범위에 비해 자체 인증 시스템을 과도하게 구현하지 않는다.

### 비용과 제약

- production 사용자 인증이 Cloudflare Access 가용성과 설정에 의존한다.
- Cloudflare Access 정책, Application audience, team name을 운영 설정으로 관리해야 한다.
- local/CI와 production의 인증 진입 경로가 다르므로 profile 분리와 통합 테스트가 필요하다.
- Spring에서 Access JWT 검증과 내부 User 매핑 코드를 구현해야 한다.

## 운영 보안 요구

- `cloudflared` production ingress는 Access 검증 `required`를 활성화하고 해당 Application의 `teamName`과 `audTag`를 사용한다.
- 실제 `audTag`, team name, tunnel credential, 허용 이메일을 저장소에 커밋하지 않는다.
- API, PostgreSQL, Nginx origin 포트를 공용 인터넷에 직접 노출하지 않는다.
- 관리 SSH와 서버 운영 접근은 Tailscale 경로를 사용한다.
- Access JWT, `CF_Authorization` cookie 및 기타 인증 credential을 로그에 남기지 않는다.

## Rejected Alternatives

### 애플리케이션 자체 비밀번호 + Spring Session

ADR-007에서 선택했으나 현재 두 사용자·Cloudflare Tunnel 구조에서는 직접 운영해야 할 인증 기능과 공격 표면이 불필요하게 커져 supersede한다.

### 애플리케이션 자체 Access/Refresh JWT

브라우저 same-origin PWA에 별도 token lifecycle을 추가할 이점이 없다.

### Tailscale만으로 사용자 접근 제한

서버 관리에는 적합하지만 여자친구의 일반 PWA 이용 기기까지 tailnet에 가입시키는 운영 부담이 있고 일반 웹/PWA 접근 경험도 나빠져 서비스 이용 경계로 사용하지 않는다.

### Cloudflare Access만 검증하고 애플리케이션 인가 생략

Access는 애플리케이션 진입 identity만 보장한다. 내부 User 상태, Household membership, IDOR 방지는 도메인 인가이므로 Spring에서 별도로 검증한다.
