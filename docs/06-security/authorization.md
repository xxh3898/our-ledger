---
status: active
version: 0.2
last_updated: 2026-08-27
related:
  - ADR-001
  - ADR-008
  - 02-domain/household.md
---

# 인가

## 기본 규칙

Cloudflare Access 인증은 애플리케이션 진입 identity를 보장할 뿐, 내부 재무 데이터 권한을 대신하지 않는다.

Spring Security와 Service Layer는 다음 순서로 인가한다.

1. 검증된 Access JWT의 email claim을 내부 활성 User에 매핑한다.
2. 해당 User가 요청 대상 Household의 활성 Member인지 확인한다.
3. 리소스를 `id + household_id` 경계로 조회한다.
4. 하위 참조도 같은 Household인지 검증한다.

frontend의 숨김 처리, 전달된 Household ID, 일반 요청 헤더를 권한 근거로 사용하지 않는다.

## 현재 Household

V1은 인증된 User의 단일 Household를 기본으로 하되, 내부 서비스와 query는 Household ID 경계를 명시한다. 미래 다중 Household 가능성이 있어도 현재 API를 불필요하게 복잡하게 만들지 않는다.

## 리소스 조회

Account, Category, Transaction, Budget, RecurringTransaction, Goal을 조회·변경할 때:

1. 현재 User의 Household를 결정한다.
2. 리소스를 `id + household_id`로 조회한다.
3. 하위 참조도 같은 Household인지 검증한다.

## Member 권한

V1에서 OWNER와 MEMBER는 재무 데이터에 동일한 CRUD 권한을 가진다.

다음 운영성 변경은 본인 또는 OWNER 범위로 제한할 수 있다.

- 내부 User 활성/비활성 상태
- Cloudflare Access identity와 내부 User 매핑 변경
- Household 구성원 변경
- 향후 Household 삭제

Cloudflare Access 정책 자체의 변경은 애플리케이션 권한이 아니라 별도 production 운영 권한으로 취급한다.

## IDOR 방지

다른 Household의 ID를 요청해도 데이터 내용, 존재 여부, 이름을 노출하지 않는다. Repository method부터 Household 조건을 포함한다.

## 인증 성공과 인가 성공의 분리

다음 요청은 Cloudflare Access를 통과했더라도 애플리케이션에서 거부한다.

- JWT email과 일치하는 내부 활성 User가 없음
- User가 해당 Household의 활성 Member가 아님
- 리소스가 다른 Household에 속함
- 요청이 허용된 Member 권한 범위를 벗어남
