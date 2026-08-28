---
status: active
version: 0.2
last_updated: 2026-08-28
related:
  - 05-frontend/design-system.md
  - 05-frontend/marriage-goal.md
  - 05-frontend/quick-entry.md
---

# Motion과 상호작용

## 상태와 범위

이 문서는 Couple-first 화면의 motion 방향을 정의한다. production dependency를 추가하거나 특정 animation library 채택을 확정하지 않는다. 각 Slice는 기능과 접근성을 먼저 구현한 뒤 필요한 motion만 추가한다.

## 기본 원칙

- 일반 press, color change, 짧은 단순 transition은 CSS를 우선한다.
- Bottom Sheet, layout change, list enter/exit, progress, cat motion은 복잡성이 실제로 필요할 때만 Motion for React를 검토한다.
- library 수를 늘리는 것을 목표로 삼지 않는다.
- `transform`과 `opacity` 중심으로 구현하고 layout thrashing을 유발하는 animation을 피한다.
- 큰 blur, glassmorphism, 무한 반복 animation을 남발하지 않는다.
- motion이 금융 숫자의 인지, 입력, 오류 확인을 지연하거나 가리지 않아야 한다.

## 대표 interaction

| 상황 | 방향 |
|---|---|
| button press | 즉각적인 color 또는 작은 scale feedback |
| Bottom Sheet | 현재 context를 유지하는 짧은 진입·종료 transition |
| Scope 선택 | 선택된 cat identity의 짧은 scale 또는 spring |
| `SHARED` 선택 | 두 고양이가 살짝 가까워지는 짧은 motion |
| Category·Account·날짜 선택 | 선택 즉시 반영하고 picker 종료, 별도 확인 motion 없음 |
| 저장 성공 | button disabled와 spinner 뒤 `저장했어요` text와 작은 Paw, 약 400~600ms 후 Sheet 종료 |
| Goal 증가 | 집 방향의 짧은 진행 표현을 검토하되 실제 수치 갱신을 방해하지 않음 |
| Goal milestone | 25%, 50%, 75%, 100%에서만 비교적 큰 celebration 허용 |

저장 실패는 Sheet와 입력값을 유지한다. 실패 상태에서 성공 animation이나 자동 닫힘을 실행하지 않는다.

## Reduced motion

`prefers-reduced-motion: reduce`를 필수로 지원한다.

- spring, 큰 이동, cat 이동, celebration을 제거하거나 즉시 상태 전환으로 대체한다.
- 필요한 경우 짧은 opacity 변화만 사용하고 정보 전달을 animation에 의존하지 않는다.
- `저장했어요`, 오류, 선택 상태 같은 text feedback은 motion 설정과 무관하게 즉시 제공한다.
- reduced motion에서도 Sheet open/close, focus 이동, 저장 완료의 기능 순서는 동일하게 유지한다.

## Focus와 조작

- Sheet와 picker가 열리면 목적에 맞는 첫 control로 focus를 이동하고 닫힌 뒤 호출한 control로 되돌린다.
- keyboard와 screen reader 사용자는 pointer motion 없이 같은 action과 상태를 확인할 수 있어야 한다.
- animation 중 submit이나 navigation을 중복 실행하지 않도록 pending 상태를 명시한다.
- duration과 easing token은 실제 구현에서 기기 성능과 접근성을 검증한 뒤 확정한다. 저장 성공 feedback의 400~600ms 외에는 mockup만 보고 고정하지 않는다.

## Slice 4 구현 상태

- 새 motion dependency 없이 CSS만 사용한다.
- Paw FAB press와 loading Paw에만 작은 scale/opacity feedback을 적용하고 `prefers-reduced-motion`에서 제거한다.
- 저장 성공 text/Paw는 즉시 표시하고 500ms 뒤 Sheet를 닫는다. 실패 상태는 움직이거나 닫지 않는다.
- Quick Entry를 닫으면 호출한 FAB 또는 수정 button으로 focus를 복귀한다.
