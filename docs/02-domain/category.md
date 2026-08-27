---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 03-data/schema-rules.md
---

# Category 도메인

## 구조

```text
Category Group
└─ Category
```

Group 없이 Category만 둘 수도 있다. Group과 Category는 `INCOME` 또는 `EXPENSE` 유형을 가진다.

## 사용자 자유도

- 생성
- 이름 변경
- Group 이동
- 순서 변경
- 보관
- `icon_key`, `color_key` 설정

대표 아이콘과 디자인 시스템은 출시 후반에 결정하지만 DB와 API에는 key 필드를 초기부터 둔다.

## 기본 Category 예시

지출: 식비, 카페, 데이트, 교통, 쇼핑, 생활, 취미, 구독, 의료, 여행, 선물, 교육, 반려동물, 기타.

수입: 급여, 부수입, 상여, 용돈, 이자, 기타수입.

기본 Category도 Household 소유 데이터로 생성해 사용자가 보관·수정할 수 있게 한다.

## 제약

- 활성 상태에서 Household·type·이름의 대소문자 무시 중복을 막는다.
- Category type과 Group type은 일치해야 한다.
- 거래가 연결된 Category는 물리삭제하지 않는다.
- 보관된 Category는 과거 거래 조회에서 표시한다.
