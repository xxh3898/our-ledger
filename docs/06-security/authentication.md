---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - ADR-007
  - 06-security/privacy-model.md
---

# 인증

## 방식

Spring Security 기반 서버 세션을 사용한다. V1은 같은 origin의 React PWA와 Spring API를 제공하므로 JWT를 도입하지 않는다.

## Cookie

- `HttpOnly`
- production에서 `Secure`
- 적절한 `SameSite`
- session fixation 방지를 위한 로그인 시 session rotation
- logout 시 서버 session 무효화

## 비밀번호

raw password를 저장·로그하지 않는다. Spring Security `DelegatingPasswordEncoder`를 사용하고 초기 hash는 BCrypt 계열로 생성한다. 비밀번호 변경과 초기 계정 provision은 별도 안전한 운영 절차로 수행한다.

## CSRF

Cookie 인증이므로 상태 변경 요청에 CSRF 방어를 적용한다. “사용자 2명뿐”이라는 이유로 비활성화하지 않는다.

## 로그인 보호

- 반복 실패 rate limit 또는 지연
- 일반화된 실패 메시지
- session ID 로그 금지
- 비활성 User 로그인 거부

## 세션 범위

모바일 PWA 사용성을 해치지 않는 만료 시간을 설정하되, 무기한 session은 사용하지 않는다. 정확한 timeout은 production gate에서 확정한다.
