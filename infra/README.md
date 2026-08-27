# Infra

Mac mini production 배포 자산이 위치한다.

예상 구성:

```text
infra/
├─ compose/
├─ nginx/
├─ cloudflare/
├─ backup/
└─ runbooks/
```

production secret, 실제 tunnel credential, DB dump는 커밋하지 않는다. 배포·백업 파일은 해당 Slice의 Issue와 운영 문서가 준비된 뒤 추가한다.
