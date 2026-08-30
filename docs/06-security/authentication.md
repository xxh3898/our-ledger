---
status: active
version: 0.4
last_updated: 2026-08-30
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

구현은 Spring Security OAuth2 Resource Server와 `NimbusJwtDecoder`를 사용한다. `Cf-Access-Jwt-Assertion` 전용 `HeaderBearerTokenResolver`가 raw JWT를 읽고 RS256 signature, `iss`, `aud`, `exp`/`nbf`, nonblank email을 검증한다. 일반 `Authorization` bearer나 임의 email header는 이 경로의 identity가 아니다.

production/default startup에는 다음 외부 설정이 모두 필요하며 하나라도 비어 있으면 fail-closed한다.

- `CLOUDFLARE_ACCESS_ISSUER`
- `CLOUDFLARE_ACCESS_JWK_SET_URI`
- `CLOUDFLARE_ACCESS_AUDIENCE`

클라이언트가 임의로 전달할 수 있는 일반 이메일 헤더만 신뢰하지 않는다.

## 내부 User Provision

Cloudflare Access 인증 성공만으로 내부 User를 자동 생성하지 않는다.

local 개발에서는 기본 비활성인 generic `ApplicationRunner` bootstrap으로 두 User를 미리 만들 수 있다. Household 이름, 두 email과 표시명은 Git 제외 local `OUR_LEDGER_BOOTSTRAP_*` 설정으로만 주입한다.

- `OUR_LEDGER_BOOTSTRAP_ENABLED=false`가 기본이다.
- clean DB에는 ACTIVE User 두 명, 한 Household, OWNER/MEMBER를 한 transaction으로 생성한다.
- 정확한 상태의 재실행은 no-op이다.
- 부분 생성, 추가 data, 다른 표시명·상태·role·Household는 덮어쓰지 않고 startup을 실패시킨다.
- 저장소에는 `example.test` sample만 둔다.

production provision은 local env runner와 분리한다. normal `production`은 bootstrap false를 강제하고 env override를 거부한다. 동일 candidate API image의 `production,bootstrap` one-shot만 최대 8 KiB exact JSON stdin을 읽으며 email은 기존 canonical normalizer를 거친다. CLI argument, Compose environment, workflow input, process title에 Household 이름·email·표시명을 넣지 않고 raw JSON, PII 또는 생성 ID를 log/stdout/stderr에 남기지 않는다. 10D-3A2 fresh-host worker도 input을 fixed owner-only file에서 stdin으로만 전달하고 pending/state에는 candidate, phase, schema와 backup marker hash만 기록한다. bootstrap mode는 Web, Cloudflare/local/test identity, Flyway와 recurring scheduler를 활성화하지 않으며 실제 input 생성·전송, ingress 설치와 production DB 실행은 10D-3B 별도 승인 대상이다.

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
- Spring Security 7 `csrf.spa()`와 `CookieCsrfTokenRepository`를 적용한다.
- server는 `XSRF-TOKEN` cookie와 `X-XSRF-TOKEN` response header를 발급한다.
- frontend는 unsafe same-origin 요청에서 cookie의 plain token을 `X-XSRF-TOKEN` request header로 보낸다.
- token이 없거나 유효하지 않은 state-changing 요청은 403으로 거부한다.
- “사용자가 두 명뿐”이라는 이유로 요청 위조 방어를 비활성화하지 않는다.

## Local / CI

local과 CI는 Cloudflare 인프라 없이 인증 흐름을 테스트한다. `local`/`test` filter chain에만 `X-Our-Ledger-Local-Identity` adapter가 존재한다.

- production/default filter chain에는 local adapter가 구조적으로 포함되지 않는다.
- `production`과 `local`/`test` profile을 함께 활성화하면 startup guard가 실패한다.
- local identity도 normalized email→ACTIVE User→정확히 하나의 Household membership을 모두 통과한다.
- Vite proxy는 server-side `OUR_LEDGER_LOCAL_IDENTITY_EMAIL`만 읽으며 browser bundle에는 값을 넣지 않는다.
- production 요청에서 Access JWT가 없거나 유효하지 않으면 실패한다.
- test identity와 RSA/JWK fixture는 `example.test` 가짜 값만 사용한다.

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
