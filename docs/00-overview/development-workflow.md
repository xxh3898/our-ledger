---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - AGENTS.md
  - .github/PULL_REQUEST_TEMPLATE.md
---

# 개발 작업 흐름

## 기본 흐름

```text
GPT 또는 사용자
→ 다음 한 PR 크기의 Issue 설계
→ Codex가 feature branch에서 구현
→ 로컬 검증과 문서 동기화
→ Pull Request 생성
→ Hosted CI
→ GPT 독립 리뷰
→ 사용자가 merge
```

## Issue 준비 기준

Issue에는 다음이 있어야 한다.

- 목표와 배경
- `IN`과 `OUT`
- 검증 가능한 수용 기준
- 관련 docs/ADR
- 재무·데이터·보안 영향
- 필수 테스트
- 중단 조건

## 구현 기준

- 한 Slice 전체가 아니라 한 Pull Request로 안전하게 검토 가능한 크기로 나눈다.
- DB schema와 API, UI를 무조건 계층별로 한꺼번에 만들지 않는다.
- 사용자에게 실제 가치를 주는 vertical path를 우선한다.
- 문서 계약이 불완전하면 임의 해석보다 결정 요청을 우선한다.

## Pull Request 상태

- Draft: 구현 또는 검증 중
- READY: 로컬 검증과 Hosted CI 완료, 독립 리뷰 대기
- MERGE: 리뷰에서 blocker 없음
- CHANGES_REQUIRED: 수정 후 재검토 필요
- HOLD: 외부 결정·운영 권한·데이터 확인 필요

## 금지

- 에이전트의 직접 merge
- 운영 배포
- 실제 secret 변경
- 승인 없는 destructive migration
- Issue 밖 대규모 리팩터링
- 검증하지 않은 계산 변경

상세 실행 규칙은 루트 `AGENTS.md`가 우선한다.
