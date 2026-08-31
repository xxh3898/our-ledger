---
status: active
version: 0.2
last_updated: 2026-09-01
related:
  - 00-overview/roadmap.md
  - 07-quality/acceptance-criteria.md
  - 07-quality/testing-strategy.md
  - 08-operations/deployment.md
---

# ADR-009: Legacy bridge를 통한 runtime-config manifest 전환

## Status

Accepted

## Context

production current application revision `9dd350b240885bb55e89720a23dd824046dfa351`의 host worker는 runtime-config release를 source에 고정된 exact file/mode set으로 검증한다. 이 계약은 unexpected material을 fail closed하는 데는 적합하지만, 다음 runtime artifact가 새 파일을 추가하면 old worker가 새 worker 자체를 설치하기 전에 artifact를 거부하는 one-way evolution trap을 만든다.

`558f92e05f1988f2288bd605348ba7bf545d0fa8`에서 발행한 runtime-config digest `sha256:62eb36546c5fb786d42724eb026d5c7aa9c6c3fc319460ee58019355e2d5eb9f`에는 encrypted offsite source 두 파일이 추가됐다. 발행은 정상 완료됐지만 old worker는 이 artifact를 accept할 수 없으므로 direct production update authority로 사용할 수 없다. 수동 file copy나 allowlist 검증 완화는 immutable artifact와 recovery authority를 훼손한다.

## Decision

runtime-config file-set 전환은 Legacy Runtime V1 bridge와 Manifested Runtime V2의 두 단계로 수행한다.

### Legacy Runtime V1

- root에 `runtime-manifest.json`이 없다.
- production `9dd350b...` worker가 아는 20개 file, mode와 그 parent directory set을 exact profile로 동결한다.
- unknown, missing, extra file/directory와 symlink, hardlink, 비정규 entry를 거부한다.
- `runtimeConfigContentSha256`은 기존 path, NUL, four-digit mode, NUL, file bytes, NUL iteration byte stream을 그대로 사용한다.
- 전환 첫 단계의 bridge Docker artifact는 이 V1 shape를 사용하며 offsite 두 파일과 manifest를 포함하지 않는다.

### Manifested Runtime V2

- root regular file `runtime-manifest.json` mode는 `0600`이다.
- manifest top-level exact keys는 `formatVersion`, `project`, `files`이고 version은 integer `2`, project는 `our-ledger`다.
- file entry exact keys는 `path`, `mode`다. list는 bounded non-empty, path는 sorted unique canonical relative POSIX이며 `compose.yaml`, `infra/...`, `scripts/...` namespace만 허용한다.
- mode는 string `0600` 또는 `0700`만 허용하고 manifest 자신은 payload list에 넣지 않는다.
- manifest와 declared payload가 actual file set과 exact 일치해야 하고 directory set은 file parents에서 exact derive한다.
- content hash는 V2 domain marker, manifest path/mode와 exact manifest bytes, 각 payload path/mode/content를 포함한다. 같은 semantic JSON이라도 bytes가 다르면 다른 immutable identity다.

### Dual-format host worker

- manifest 부재는 V1으로만, 존재는 V2로만 분류하며 두 profile에 정확히 속하지 않으면 거부한다.
- candidate image의 exact digest, linux/arm64, OCI revision/version 검증을 manifest가 대체하지 않는다.
- archive는 `/runtime` subtree를 추출 전에 분류하고 exact member/type/mode/size를 확인한다. traversal, duplicate, symlink/hardlink/device/FIFO/socket과 broad `extractall`을 허용하지 않는다.
- extracted tree는 동일 host validator로 다시 검증한다.
- stage는 source profile과 hash를 copy 전후 재확인하고 owner-only file/directory fsync 뒤 immutable release를 publish한다.
- `ReleaseIdentity`, current, state와 pending JSON schema는 변경하지 않는다. V1과 V2 release는 같은 releases authority 아래 공존할 수 있다.

### 전환 순서

1. Legacy V1 shape이면서 dual-format worker를 포함한 bridge source를 release/publish한다.
2. production old V1 worker로 bridge V1 artifact를 update한다.
3. 별도 source Gate에서 V2 manifest artifact와 offsite 두 파일을 활성화한다. Issue #93이 이 source 단계를 완료한다.
4. V2를 release/publish한 뒤 bridge worker로 production update한다.

각 release, publish와 production update는 별도 승인 Gate다. 이번 결정 자체는 production 또는 GHCR mutation을 승인하지 않는다.

Issue #93의 source 결과는 root `runtime-manifest.json` mode `0600`, manifest가 선언한 exact 22개 payload와 7개 parent directory를 `scratch` linux/arm64 artifact로 구성한다. actual build/export archive는 bridge extractor로 preflight·member별 추출하고 동일 host validator로 re-read한 뒤 immutable stage/content hash까지 합성 경로에서 검증한다. 이는 전환 3단계의 source/CI 완료일 뿐 4단계의 GHCR release/publish, Mac mini pull/stage/current 전환 또는 encrypted offsite 실행을 뜻하지 않는다.

## Consequences

### 장점

- old worker의 fail-closed allowlist를 약화하지 않고 다음 worker를 설치할 수 있다.
- 이후 runtime file 추가/삭제는 source code의 global allowlist 교체가 아니라 immutable manifest 변경으로 표현된다.
- V1 content hash와 existing current/state를 byte-compatible하게 읽는다.
- V2 archive와 host release가 같은 parser/validator authority를 공유한다.

### 비용과 위험

- bridge와 최종 V2를 각각 release/publish/update해야 하므로 전환 단계가 늘어난다.
- V2 source artifact에는 offsite 실행 파일이 포함되지만 실제 encrypted offsite activation은 별도 V2 release/publish/host update와 운영 설정 승인까지 지연된다.
- exact manifest bytes를 hash하므로 의미가 같은 formatting 변경도 새 content identity가 된다.
- manifest는 artifact digest를 대체하지 않으며 registry/host transition의 각 검증을 계속 유지해야 한다.

## Rejected Alternatives

### old host에 새 파일을 수동 복사

artifact digest, content identity와 atomic stage 계약 밖의 mutation이 되어 recovery와 audit authority를 잃으므로 거절한다.

### old worker의 allowlist를 임시로 완화

새 worker를 설치하기 전에 production source를 바꿔야 하는 동일한 bootstrap 문제를 해결하지 못하고 unexpected material 방어를 약화하므로 거절한다.

### 앞으로도 release마다 global fixed allowlist 교체

매번 현재 worker가 다음 file set을 거부하는 evolution trap이 반복되므로 거절한다.

## Migration / Rollback

source 단계의 rollback은 Manifested V2 source commit을 revert해 V1 bridge Dockerfile과 gate로 돌아간다. frozen V1 validator/reference hash와 current/state schema는 계속 유효하다. V2 release/publish 또는 host update는 이 source Gate에서 실행하지 않았으며, 이후 V2가 current가 된 뒤의 host rollback은 candidate schema와 transaction authority를 별도 검토한다. 자동 DB restore, reverse migration, runtime directory 삭제는 이 ADR 범위가 아니다.
