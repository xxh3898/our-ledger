---
status: active
version: 0.5
last_updated: 2026-09-09
related:
  - 06-security/authentication.md
---

# PWA 정책

## 현재 상태

Slice 10B 전체는 최종 한글 앱 이름과 production icon이 결정될 때까지 HOLD다. 다만 Calendar 새 실행의 날짜 권한을 위해 최소 Web App Manifest를 제공한다. 이 manifest는 `start_url=/`, `scope=/`, `display=standalone`만 고정하며 기존 URL의 날짜를 application heuristic으로 초기화하지 않는다.

최종 앱 이름·icon, service worker, install prompt, offline app shell은 여전히 구현하지 않는다. 최소 manifest를 전체 PWA 완료나 설치 품질 acceptance로 간주하지 않는다.

## 목적

네이티브 앱 없이 모바일 홈 화면 설치, standalone 실행, 빠른 시작 경험을 제공한다.

## Viewport와 확대

- 문서는 `width=device-width, initial-scale=1.0` viewport를 사용한다.
- 사용자의 pinch zoom은 허용한다. `maximum-scale=1`, `user-scalable=no` 같은 접근성 저해 설정을 추가하지 않는다.
- mobile form control은 16px 이상의 실제 입력 typography를 사용해 Safari input focus의 의도하지 않은 auto-zoom을 피한다.
- standalone PWA와 Safari 모두 page-level horizontal overflow 없이 세로 scroll 중심으로 동작해야 한다. Sheet가 열리거나 keyboard로 viewport 높이가 줄어도 width는 viewport를 넘지 않는다.
- browser viewport simulation은 layout 진단 증거일 뿐 Safari/Home Screen PWA 실기기 PASS를 대신하지 않는다. 지원하는 실제 iPhone 모델의 focus, keyboard, Sheet, pinch zoom을 최종 smoke한다.

## 캐시

캐시 가능:

- versioned JS/CSS
- app shell
- icon과 정적 이미지
- manifest

캐시 금지 또는 network-only:

- `/api/**`의 재무 응답
- 인증·인가 및 Access 재인증 관련 응답
- CSV export

Service Worker가 오래된 거래·잔액·목표 금액을 보여주지 않게 한다.

## 오프라인

V1은 오프라인 쓰기를 지원하지 않는다. 네트워크가 없으면 읽기 가능한 app shell과 명확한 연결 오류를 제공하고 거래 저장을 queue하지 않는다.

## 설치 자산

- favicon
- 192x192 icon
- 512x512 icon
- maskable 512x512 icon

대표 아이콘 디자인은 기능·UI 확정 후 진행한다.

## 업데이트

새 Service Worker가 준비되면 사용자가 안전하게 새로고침할 수 있게 안내한다. 입력 중 강제 reload하지 않는다.
