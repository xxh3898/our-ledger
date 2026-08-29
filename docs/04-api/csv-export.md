---
status: active
version: 0.1
last_updated: 2026-08-29
related:
  - 04-api/api-conventions.md
  - 03-data/data-retention.md
  - 06-security/privacy-model.md
  - 08-operations/backup-restore.md
---

# CSV 거래 내보내기

## 목적과 경계

CSV는 current Household의 유효 거래를 사용자가 스프레드시트에서 검산하고 이동하기 위한 동기 export다. 운영 backup, 삭제 데이터 복원, 전체 schema dump가 아니다.

```http
GET /api/v1/exports/transactions.csv?from=2026-08-01&to=2026-08-29
```

`from`과 `to`는 Household timezone의 포함 날짜이며 최대 범위는 시작일 포함 3,653일이다. 다른 Household ID나 세부 filter는 받지 않는다.

## 응답

```text
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="our-ledger-transactions_<from>_<to>.csv"
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

- body 처음에 UTF-8 BOM을 정확히 한 번 둔다.
- delimiter는 comma, record line ending은 CRLF이고 마지막 record도 CRLF로 끝난다.
- comma, double quote, CR 또는 LF가 있는 cell은 double quote로 감싸며 내부 double quote는 두 번 쓴다.
- nullable 값은 빈 cell이다.
- 서버에 CSV 파일이나 export history를 저장하지 않는다.

## 고정 column

| 순서 | Header | 의미 |
|---:|---|---|
| 1 | 거래ID | Transaction ID |
| 2 | 발생일 | Household local `YYYY-MM-DD` |
| 3 | 발생시각 | Household local ISO 8601 offset datetime |
| 4 | 거래유형 | `수입`, `지출`, `이체` |
| 5 | 조정유형 | `일반`, `환불` |
| 6 | 금액 | 양수 KRW 정수 |
| 7 | 귀속 | `개인`, `공동`; TRANSFER는 빈 값 |
| 8 | 소유자 | PERSONAL owner 표시명 |
| 9 | 결제자 | EXPENSE payer 표시명 |
| 10 | 카테고리 | INCOME/EXPENSE Category 이름 |
| 11 | 계좌 | INCOME/EXPENSE PRIMARY Account 이름 |
| 12 | 출금계좌 | TRANSFER SOURCE Account 이름 |
| 13 | 입금계좌 | TRANSFER DESTINATION Account 이름 |
| 14 | 메모 | nullable memo |
| 15 | 원거래ID | REFUND의 original Transaction ID |
| 16 | 반복거래 | generated이면 `예`, 아니면 `아니오` |
| 17 | 반복발생일 | generated recurrence date |
| 18 | 생성시각 | UTC ISO 8601 Instant |
| 19 | 수정시각 | UTC ISO 8601 Instant |

한 Transaction당 한 row이며 `occurred_at ASC, id ASC`로 정렬한다. 카드 지출은 `지출`, 카드대금 납부는 `이체`, REFUND는 별도 `지출/환불` row다. generated recurring Transaction은 일반 원장 row로 포함하고 provenance를 표시한다. 논리삭제는 제외하며 archived Account/Category 이름은 유지한다.

## Spreadsheet formula 방어

Member 표시명, Category 이름, Account 이름, memo처럼 사용자 또는 기준정보에서 온 text만 검사한다. 원문 첫 글자 또는 `strip()` 뒤 첫 글자가 다음 중 하나면 CSV escape 전에 ASCII apostrophe `'`를 원문 맨 앞에 한 글자 붙인다.

```text
=  +  -  @  TAB  CR
```

예를 들어 `=SUM(A1:A2)`는 `'=SUM(A1:A2)`, `  =cmd`는 `'  =cmd`가 된다. Excel, LibreOffice, Google Sheets가 formula로 실행할 수 없는 text prefix이며, 원문 복원 시 방어 apostrophe 한 글자만 제거하면 된다. 숫자, enum, 날짜, 서버 생성 ID에는 적용하지 않는다. CSV quoting만으로 formula 방어를 대신하지 않는다.

## Backend read plan과 fail-closed

1. `CurrentHousehold`에서 tenant와 timezone을 정한다.
2. `[fromStart, toPlusOneStart)`와 `deleted_at IS NULL`로 Transaction을 조회한다.
3. 대상 Entry와 current Household의 Account, Category, Member를 각각 한 번씩 batch 조회한다.
4. 기존 Transaction 조회와 같은 canonical Entry validator로 모든 row를 검사한다.
5. 검증이 끝난 뒤 메모리에서 CSV byte를 만든다.

따라서 result 유무와 무관하게 Transaction별/Account별 N+1이 없고 대상이 있을 때 SQL query는 최대 5개다. 손상 Entry는 `409 TRANSACTION_ENTRY_SET_INVALID`, 날짜 오류는 `400 INVALID_REQUEST`, 3,653일 초과는 `422 EXPORT_RANGE_TOO_LARGE` JSON으로 반환한다.

## Frontend

Settings의 `데이터 내보내기`에서 시작일과 종료일을 받는다. 기본값은 Household timezone 현재 월 1일부터 오늘이다. pending 중 요청을 중복하지 않고 오류 뒤 입력을 유지한다.

성공 response의 media type이 `text/csv`인지 확인하고 `our-ledger-transactions_YYYY-MM-DD_YYYY-MM-DD.csv` 형식의 server filename만 사용한다. 그 외에는 현재 요청 날짜 기반 고정 filename으로 대체한다. Blob object URL로 download를 시작한 직후 URL을 revoke하며 Settings와 keyboard focus를 유지한다.

## 개인정보와 운영 경계

- Account/Card 전체 번호, `lastFour`, email, token, cookie, CSRF credential, secret을 포함하지 않는다.
- CSV body와 전체 memo를 application log에 기록하지 않는다.
- same-origin 인증 cookie는 browser가 전송하며 frontend storage나 임의 header로 복제하지 않는다.
- CSV 생성은 DB write, lock, migration, temp file, background job을 만들지 않는다.
- 실제 backup/restore, PWA, Cloudflare 설정, deploy는 별도 Slice 10B~10D Gate다.
