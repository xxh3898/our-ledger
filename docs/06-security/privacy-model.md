---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - ADR-008
  - 03-data/data-retention.md
  - 08-operations/deployment.md
---

# 개인정보 모델

## 공개 범위

이 제품을 함께 사용하는 두 Member는 상대방의 개인 수입과 소비를 볼 수 있다는 전제에 명시적으로 동의한다. `PERSONAL`은 상대방에게 비공개라는 뜻이 아니라 소비 귀속 구분이다.

## 최소 수집

필수:

- Cloudflare Access identity와 매핑하기 위한 이메일
- 표시명
- 내부 User 상태
- 거래·계좌·예산·목표 정보

애플리케이션 V1에서 수집·저장하지 않음:

- 사용자 비밀번호
- `password_hash`
- 주민등록번호
- 전체 계좌번호
- 전체 카드번호
- 은행 로그인 정보
- 카드사 인증정보
- OTP
- Cloudflare Access/Tunnel credential

실제 허용 이메일은 Cloudflare Access 운영 설정과 내부 User provision에 필요하지만 저장소 코드·문서에는 커밋하지 않는다.

## 외부 인증정보

Cloudflare Access는 외부 identity provider 역할을 한다. 애플리케이션은 검증된 Access JWT의 email claim을 내부 User에 매핑하는 데 필요한 최소 정보만 사용한다.

Access JWT 전체 값이나 Access session cookie를 애플리케이션 데이터베이스에 저장하지 않는다.

## 로그

금지:

- `Cf-Access-Jwt-Assertion` 전체 값
- `CF_Authorization` cookie
- OTP
- Cloudflare/Tunnel credential
- CSRF credential
- 전체 memo/body 무차별 기록
- 전체 금융 식별정보

오류 분석에 필요한 내부 ID, error code, traceId만 남긴다. 인증 실패 로그가 필요하더라도 token 원문을 기록하지 않는다.

## Export

CSV는 사용자 재무 데이터 이동성을 제공한다. export 요청도 내부 User 및 Household 권한을 검증하고 임시 파일을 장기 보관하지 않는다.

## 운영자 접근

Mac mini와 DB shell 접근은 Tailscale 등 관리 경로로 제한한다. Cloudflare Access 정책 변경과 내부 User provision도 운영 작업으로 취급한다. 운영자가 실데이터를 조회하는 절차는 필요성과 최소 범위를 기록한다.

## 미결정

출시 전 사용자 비활성화, Household 해체, backup 파기, 보존기간 정책을 확정해야 한다.
