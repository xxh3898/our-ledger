---
status: active
version: 1.0
last_updated: 2026-08-28
related:
  - 02-domain/recurring-transaction.md
  - 04-api/api-conventions.md
  - 05-frontend/information-architecture.md
---

# 반복 거래 설정

## 진입과 범위

반복 거래는 설정 Sheet 안의 `반복 거래` section에서 관리한다. 별도 하단 탐색 destination이나 자동 생성 전용 원장 화면을 만들지 않는다. 목록은 active, paused, ended 규칙을 모두 유지해 사용자가 현재 상태와 다음 발생일을 확인할 수 있게 한다.

## 목록

각 규칙은 이름, 금액, `활성`·`일시정지`·`종료` 상태, schedule, Account, PERSONAL Member 또는 공동 subject를 표시한다. active 규칙은 다음 발생일을, ended 규칙은 종료됐음을 명시한다. 규칙 선택은 편집 Sheet를 열고, 목록 action은 일시정지 또는 재개를 제공한다.

재개 action 근처에는 `일시정지 중 발생일은 소급 생성하지 않습니다.`를 항상 표시한다. 서버가 반환한 상태와 cursor를 source of truth로 사용하고 frontend가 누락 발생일을 계산하거나 생성하지 않는다.

## 생성과 수정 Sheet

Sheet는 다음 입력을 제공한다.

- 이름, 거래 유형, 금액
- PERSONAL/SHARED Scope와 실제 Member owner/payer
- Category와 PRIMARY Account 또는 이체 SOURCE/DESTINATION Account
- DAILY/WEEKLY/MONTHLY/YEARLY, positive interval
- 시작일, 선택 종료일, Household local 실행 시각
- 선택 메모

V1은 `autoPost=true`만 지원한다. active Account와 Category만 새 template 선택지로 제공한다. MONTHLY/YEARLY에는 시작일의 원래 anchor를 보존하고 짧은 달·윤년에 마지막 유효일로 조정한다는 설명을 표시한다.

저장 중에는 중복 submit을 막는다. 실패하면 Sheet와 입력을 유지하고 안정적인 server error message를 표시한다. 성공하면 목록을 다시 조회하고 Sheet를 닫는다. nested Sheet는 첫 입력에 focus하고 Escape, backdrop, 닫기 button을 지원하며 닫힌 뒤 opener로 focus를 복귀한다.

## 생성 거래 표시

자동 생성 Transaction은 일반 원장과 같은 수정·논리삭제·집계 계약을 사용한다. 다음 위치에서 server provenance가 있는 항목에만 text `반복` badge를 표시한다.

- Calendar 선택일 거래 목록
- Budget 사용 내역 Sheet
- Statistics Transaction drill-down
- Statistics 저축 활동 Sheet

색만으로 자동 생성을 표현하지 않는다. 규칙 수정은 이미 생성된 거래를 바꾸지 않으므로 과거 항목의 badge와 금액·분류는 그대로 유지한다.
