---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - ADR-001
  - 02-domain/household.md
---

# 인가

## 기본 규칙

인증된 User가 요청 대상 Household의 활성 Member인지 서버에서 확인한다. frontend의 숨김 처리나 전달된 Household ID를 권한 근거로 사용하지 않는다.

## 현재 Household

V1은 로그인 사용자의 단일 Household를 기본으로 하되, 내부 서비스와 query는 Household ID 경계를 명시한다. 미래 다중 Household 가능성이 있어도 현재 API를 불필요하게 복잡하게 만들지 않는다.

## 리소스 조회

Account, Category, Transaction, Budget, RecurringTransaction, Goal을 조회·변경할 때:

1. 현재 User의 Household를 결정한다.
2. 리소스를 `id + household_id`로 조회한다.
3. 하위 참조도 같은 Household인지 검증한다.

## Member 권한

V1에서 OWNER와 MEMBER는 재무 데이터에 동일한 CRUD 권한을 가진다. 다음은 본인 또는 OWNER 범위로 제한할 수 있다.

- 사용자 계정 상태
- 비밀번호 변경
- Household 구성원 변경
- 향후 Household 삭제

## IDOR 방지

다른 Household의 ID를 요청해도 데이터 내용, 존재 여부, 이름을 노출하지 않는다. Repository method부터 Household 조건을 포함한다.
