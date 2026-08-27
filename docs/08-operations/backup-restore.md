---
status: active
version: 0.1
last_updated: 2026-08-27
related:
  - 03-data/data-retention.md
  - 07-quality/acceptance-criteria.md
---

# 백업과 복구

## 목표

단일 Mac mini와 단일 PostgreSQL은 장애 시 데이터 손실 가능성이 있다. backup은 같은 디스크의 복사본만으로 끝내지 않는다.

## Backup

- `pg_dump` custom format 또는 검증 가능한 형식
- 파일명에 환경·UTC 시각·schema version 식별 가능 정보 포함
- backup 종료코드와 파일 크기 검증
- 암호화된 외부 저장 위치로 복제
- secret과 backup 파일은 Git에 저장하지 않음

## 보관기간

정확한 일·주·월 보관 개수는 production gate에서 저장공간과 복구목표를 기준으로 확정한다. 확정 전 실행 보류 항목이다.

## Restore Drill

출시 전 별도 PostgreSQL instance에서 다음을 검증한다.

1. 빈 DB 생성
2. backup restore
3. Flyway schema history 확인
4. 핵심 테이블 row count
5. 두 사용자 로그인 불가 환경에서는 데이터 무결성 query 수행
6. 잔액·거래·Goal 표본 검산
7. 복구 소요시간 기록

backup 성공 로그만으로 복구 가능성을 주장하지 않는다.

## 복구 우선순위

1. production 쓰기 중지
2. 사고 시점과 최신 정상 backup 확인
3. 원본 보존
4. 별도 환경 restore 검증
5. 복구 대상 시점 확정
6. production 교체
7. 사용자에게 누락 가능 기간 명시

## CSV

사용자 CSV export는 운영 backup의 대체물이 아니다. CSV는 데이터 이동성과 수동 확인을 위한 기능이다.
