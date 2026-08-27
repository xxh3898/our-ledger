---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - ADR-008
  - 06-security/privacy-model.md
  - 06-security/authorization.md
---

# 인증

## Production 인증 경계

V1 production은 Cloudflare Access를 외부 인증 경계로 사용한다.

```text
사용자 브라우저/PWA
→ Cloudflare Access
→ 허용 이메일 정책 + OTP/IdP 인증
→ Cloudflare Tunnel
→ cloudflared Access JWT 검증
→ Nginx
→ Spring Security Access JWT 검증
→ 내부 User 매핑
```

애플리케이션 자체 이메일/비밀번호 로그인은 제공하지 않는다.

## 허용 사용자

- Cloudflare Access Allow 정책에는 실제 사용자 두 명의 이메일만 명시한다.
- 단순히 One-time PIN 로그인 방법 전체를 Include하여 모든 이메일을 허용하지 않는다.
- 실제 이메일 주소는 저장소에 커밋하지 않는다.
- 인증 방식은 One-time PIN 또는 운영자가 별도로 연결한 IdP를 사용할 수 있다.

## Access JWT

Cloudflare Access가 origin으로 전달하는 `Cf-Access-Jwt-Assertion`을 identity 검증 대상으로 사용한다.

production에서 다음을 모두 요구한다.

1. `cloudflared`가 해당 Access Application의 JWT를 검증한 요청만 origin으로 프록시한다.
2. Spring Security가 JWT 서명, issuer(`iss`), audience(`aud`), 만료를 검증한다.
3. 검증된 email claim을 정규화해 내부 활성 User를 조회한다.
4. 일치하는 User가 없으면 403으로 거부한다.
5. 이후 Household membership은 별도 인가 단계에서 확인한다.

클라이언트가 임의로 전달할 수 있는 일반 이메일 헤더만 신뢰하지 않는다.

## 내부 User Provision

Cloudflare Access 인증 성공만으로 내부 User를 자동 생성하지 않는다.

V1의 두 User는 별도 bootstrap/provision 절차로 미리 생성한다. 실제 이메일과 production 설정은 저장소 밖에서 주입한다. 정확한 bootstrap 방식은 Auth/Household Slice에서 구현 계약과 함께 확정한다.

## 비밀번호와 애플리케이션 세션

V1 production 애플리케이션은 다음을 운영하지 않는다.

- 사용자 비밀번호
- `password_hash`
- 비밀번호 변경/복구
- 자체 로그인 실패 횟수 및 계정 잠금
- 애플리케이션 자체 Access/Refresh JWT

Cloudflare Access의 인증 session과 내부 재무 권한은 별도 책임으로 본다.

## CSRF / 요청 위조 방어

Cloudflare Access를 사용해도 브라우저에서 자동으로 전달되는 인증 상태가 존재하므로 state-changing 요청의 위조 방어를 제거하지 않는다.

- PWA와 API는 same-origin을 기본으로 한다.
- Spring Security에서 CSRF 또는 동등한 Origin 기반 검증을 적용한다.
- 구체적인 token 전달 방식은 Auth/Household Slice에서 frontend 통합 테스트와 함께 고정한다.
- “사용자가 두 명뿐”이라는 이유로 요청 위조 방어를 비활성화하지 않는다.

## Local / CI

local과 CI는 Cloudflare 인프라 없이 인증 흐름을 테스트할 수 있어야 한다. 개발·테스트 전용 identity adapter 또는 test principal 주입을 허용할 수 있으나 다음을 강제한다.

- production profile에서는 활성화 불가
- production 요청에서 Access JWT가 없거나 유효하지 않으면 실패
- test identity가 실제 production email/credential을 필요로 하지 않음

## 인증정보 로그 금지

다음을 로그에 남기지 않는다.

- `Cf-Access-Jwt-Assertion`
- `CF_Authorization` cookie
- OTP
- Cloudflare/Tunnel credential
- CSRF credential
- 기타 인증 token 전체 값

## Session Duration

Cloudflare Access session duration은 모바일 PWA 사용성과 금융 데이터 민감도를 함께 고려해 production gate에서 확정한다. 무기한 접근은 사용하지 않는다.
