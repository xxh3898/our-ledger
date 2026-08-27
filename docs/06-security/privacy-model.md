---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 03-data/data-retention.md
  - 08-operations/deployment.md
---

# 개인정보 모델

## 공개 범위

이 제품을 함께 사용하는 두 Member는 상대방의 개인 수입과 소비를 볼 수 있다는 전제에 명시적으로 동의한다. `PERSONAL`은 상대방에게 비공개라는 뜻이 아니라 소비 귀속 구분이다.

## 최소 수집

필수:

- 이메일
- 표시명
- password hash
- 거래·계좌·예산·목표 정보

미수집:

- 주민등록번호
- 전체 계좌번호
- 전체 카드번호
- 은행 로그인 정보
- 카드사 인증정보

## 로그

금지:

- 비밀번호
- session cookie
- CSRF token
- 전체 memo/body 무차별 기록
- 전체 금융 식별정보

오류 분석에 필요한 ID, error code, traceId만 남긴다.

## Export

CSV는 사용자 재무 데이터 이동성을 제공한다. export 요청도 Household 권한을 검증하고 임시 파일을 장기 보관하지 않는다.

## 운영자 접근

Mac mini와 DB shell 접근은 Tailscale 등 관리 경로로 제한한다. 운영자가 실데이터를 조회하는 절차는 필요성과 최소 범위를 기록한다.

## 미결정

출시 전 사용자 탈퇴, Household 해체, backup 파기, 보존기간 정책을 확정해야 한다.
