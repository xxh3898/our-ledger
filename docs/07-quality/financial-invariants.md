---
status: active
version: 0.3
last_updated: 2026-08-29
related:
  - 02-domain/financial-metrics.md
  - 03-data/transaction-ledger-rules.md
---

# 재무 불변식

다음 항목은 자동화 테스트가 필요한 출시 차단 조건이다.

1. `TRANSFER`는 총수입과 순소비를 변경하지 않는다.
2. ASSET에서 ASSET으로 이체하면 총자산과 순자산이 변하지 않는다.
3. ASSET에서 LIABILITY로 카드대금을 납부하면 순자산이 변하지 않고 소비도 증가하지 않는다.
4. 신용카드 `NORMAL EXPENSE`는 순소비와 LIABILITY 잔액을 같은 금액만큼 증가시킨다.
5. ASSET `NORMAL EXPENSE`는 순소비를 증가시키고 ASSET 잔액을 감소시킨다.
6. `REFUND`는 원 거래의 순소비를 감소시키고 계좌 효과를 반대로 적용한다.
7. 동일 원 거래의 누적 환불액은 원 거래액을 초과할 수 없다.
8. 삭제된 Transaction과 Entry는 모든 잔액·지표·Budget·Goal 계산에서 제외된다.
9. 다른 Household의 Member, Account, Category, Transaction, Goal을 참조할 수 없다.
10. 동일 반복규칙과 recurrence date로 실제 거래가 두 번 생성될 수 없다.
11. 저축계좌에서 저축계좌로 이동한 금액은 신규 저축액이 아니다.
12. 비저축 ASSET에서 저축 ASSET으로의 순이체만 저축액에 반영한다.
13. Goal 현재 보유금은 연결 Account의 유효 잔액과 일치한다.
14. Goal 기여금을 별도 수동 합계로 저장해 Transaction과 이중 집계하지 않는다.
15. LIABILITY 잔액은 양수 부채로 저장하고 순자산 계산에서 차감한다.
16. `amount`는 양수이며 음수 방향은 Entry 또는 REFUND 의미로만 표현한다.
17. Household timezone의 월 경계가 달력·Budget·통계에서 동일하다.
18. 총수입이 0이면 저축률은 0%가 아니라 계산 불가 `null`이다.
19. Refund는 원 NORMAL EXPENSE의 Scope, Owner, Payer, Category, PRIMARY Account를 상속한다.
20. active Refund가 있는 원 거래의 금융 edit/delete는 lineage를 깨뜨릴 수 없다.
21. 동시 Refund 생성도 original row lock 경계에서 직렬화돼 누적 상한을 우회할 수 없다.
22. 반복 규칙 자체는 잔액·Budget·통계에 포함되지 않고 실제 생성된 canonical Transaction과 Entry만 포함된다.
23. 반복 생성은 규칙 row lock 안에서 due 여부를 다시 확인하며 Transaction 저장과 다음 cursor 이동이 원자적으로 완료된다.
24. 동일 `(generated_from_recurring_id, recurrence_date)`는 생성 거래가 논리삭제돼도 다시 만들 수 없다.
25. MONTHLY/YEARLY 반복은 최초 start date anchor를 유지하고 짧은 달·윤년에는 마지막 유효일로 clamp한다.
26. 규칙 template 수정은 기존 생성 거래를 변경하지 않으며 일시정지 중 발생일은 재개 시 소급 생성하지 않는다.
27. Goal `starting_balance`는 연결 audit snapshot일 뿐 현재 보유금에 다시 더하지 않는다.
28. Goal 순저축은 연결 시점 이후 비Goal→Goal TRANSFER는 양수, Goal→비Goal은 음수, Goal Account 사이 이동은 0이다.
29. Goal Account의 INCOME/EXPENSE/REFUND는 current balance에는 반영하지만 Goal 순저축 Transfer로 오분류하지 않는다.
30. 같은 Household의 MARRIAGE Goal은 하나이며 같은 Account는 둘 이상의 Goal에 동시에 연결될 수 없다.
31. Goal Account link snapshot과 같은 Account Transaction posting은 Account row lock에서 직렬화돼 partial balance를 저장할 수 없다.
32. 이미 연결된 archived Account는 unlink 전까지 실제 잔액과 함께 Goal에 남는다.
33. Goal target의 동시 PATCH는 optimistic version으로 한 요청만 반영한다.

각 Slice는 관련 불변식의 단위·통합 테스트를 추가한다. 일반 happy path 테스트만으로 완료 처리하지 않는다.
