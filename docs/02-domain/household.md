---
status: active
version: 0.3
last_updated: 2026-08-27
related:
  - ADR-001
  - ADR-008
  - 06-security/authorization.md
---

# Household 도메인

## 역할

`Household`는 모든 재무 데이터의 tenant boundary다. User는 `HouseholdMember`를 통해 Household에 참여한다.

## V1 정책

- 하나의 Household에는 활성 Member가 최대 2명이다.
- 두 Member 모두 거래, 예산, Account, Category, Goal을 조회·관리할 수 있다.
- 역할은 `OWNER`, `MEMBER`를 둔다.
- 개인 소비는 상대 Member에게 비공개가 아니다.
- production 외부 identity는 Cloudflare Access의 검증된 이메일을 내부 User에 매핑한다.
- 애플리케이션 자체 사용자 비밀번호는 V1에서 관리하지 않는다.

## User identity 규칙

- `users.email`은 Cloudflare Access identity와 내부 User를 연결하는 정규화 식별자다.
- Cloudflare Access 인증 성공만으로 내부 User를 자동 생성하지 않는다.
- 내부 User는 별도 bootstrap/provision 절차로 생성하고 활성 상태를 관리한다.
- 검증된 Access identity와 일치하는 활성 User가 없으면 접근을 거부한다.
- Access 인증과 Household membership은 별도 검증한다.

## 현재 Household 계약

- V1 API는 인증된 User의 membership이 정확히 하나일 때만 current Household를 만든다.
- membership이 없으면 `HOUSEHOLD_MEMBERSHIP_REQUIRED`, 둘 이상이면 `HOUSEHOLD_MEMBERSHIP_AMBIGUOUS`로 fail-closed한다.
- current Household ID는 검증된 내부 principal에서만 가져오며 path, query, 일반 header로 선택하지 않는다.
- `HouseholdMember`에는 별도 활성 상태가 없다. V1에서는 존재하는 membership row가 참여 상태다.

## 2인 불변식

- `(household_id, user_id)` 중복과 하나의 Household에 두 번째 `OWNER`가 생기는 경우는 PostgreSQL unique 제약으로 차단한다.
- 3번째 Member는 `Household` row를 잠근 service transaction에서 count를 확인해 차단한다.
- direct SQL은 2명 service 불변식을 우회할 수 있으므로 membership 생성은 애플리케이션 service 또는 검증된 bootstrap 경로만 사용한다.

## 초기 Bootstrap

- 기본값은 비활성이며 `our-ledger.bootstrap.enabled=true`일 때만 startup runner가 실행된다.
- Household 이름, owner/member email과 표시명은 외부 설정으로 주입하며 저장소 sample은 `example.test`만 사용한다.
- clean 상태에는 ACTIVE User 두 명, `KRW`/`Asia/Seoul` Household 한 개, `OWNER`/`MEMBER` membership을 한 transaction으로 만든다.
- 정확히 같은 상태의 재실행은 no-op이다. 부분 생성, 추가 data, 다른 표시명·상태·role·Household는 덮어쓰지 않고 fail-fast한다.
- 실제 production DB provision은 별도 운영 gate다.

## 불변 조건

- 모든 Account, Category, Transaction, Budget, RecurringTransaction, Goal은 하나의 Household에 속한다.
- 요청 사용자가 해당 Household의 활성 Member가 아니면 접근을 거부한다.
- 하위 엔티티 참조 시 ID뿐 아니라 Household 일치도 검증한다.
- 다른 Household의 ID 존재 여부가 오류 응답에서 노출되지 않게 한다.
- 외부 identity가 유효하더라도 Household membership이 없으면 재무 데이터에 접근할 수 없다.

## 삭제

V1에서 Household 자체 삭제 UI는 제공하지 않는다. 실제 운영 데이터 삭제는 백업과 복구 가능성을 확인한 별도 관리 절차로만 수행한다.
