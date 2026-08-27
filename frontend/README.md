# Frontend

React 19.2 + TypeScript 6.0 + Vite 8.x 기반 PWA가 위치한다.

Slice 0 bootstrap 후 lockfile, `.nvmrc`, lint, typecheck, test, build script를 반드시 커밋한다.

```text
frontend/
├─ package.json
├─ package-lock.json
├─ .nvmrc
├─ src/
├─ public/
└─ vite.config.ts
```

모바일 우선, 달력 중심 정보구조, API 응답 캐시 금지 정책을 따른다.
