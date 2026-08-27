---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 06-security/authentication.md
---

# PWA 정책

## 목적

네이티브 앱 없이 모바일 홈 화면 설치, standalone 실행, 빠른 시작 경험을 제공한다.

## 캐시

캐시 가능:

- versioned JS/CSS
- app shell
- icon과 정적 이미지
- manifest

캐시 금지 또는 network-only:

- `/api/**`의 재무 응답
- 인증·세션 응답
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
