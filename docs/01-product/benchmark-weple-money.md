---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 01-product/product-principles.md
  - 05-frontend/information-architecture.md
---

# Weple Money Pro 벤치마킹 원칙

이 문서는 특정 화면이나 자산을 복제하기 위한 문서가 아니다. 실제 사용 경험에서 확인한 강점을 제품 원칙으로 추출한다.

## 가져올 구조

- 달력을 핵심 탐색축으로 사용
- 일반 거래의 빠른 입력
- 카테고리와 결제수단의 높은 사용자 자유도
- 예산, 통계, 자산을 과도하게 복잡하지 않게 제공
- 반복내역으로 고정비 입력 부담 감소
- 세부 기능은 필요할 때 노출

## 차별점

`our-ledger`는 개인 가계부가 아니라 다음을 추가한다.

- 두 사용자의 개인 수입·소비를 같은 Household에서 관리
- `PERSONAL / SHARED` 전역 필터
- Payer와 Owner 분리
- 공동 자산과 부채
- 계좌 기반 결혼자금 Goal
- 정산이 아닌 공동 재무 운영

## 복제하지 않을 것

- 상표, 로고, 화면 자산, 문구, 고유한 시각 디자인
- 기능 위치와 상호작용을 그대로 재현하는 것
- iOS 전용 위젯이나 네이티브 기능

## 판단 기준

기능이 추가돼도 일반 거래 입력 단계가 늘어나거나 달력 화면이 복잡해지면 벤치마킹 취지와 어긋난다. 고급 기능은 progressive disclosure를 사용한다.
