# Frontend

React 19.2.8 + TypeScript 6.0.3 + Vite 8.2.2 기반 frontend다. Node.js 24.20.0은 `.nvmrc`, dependency는 `package-lock.json`으로 고정한다.

## 실행

개발 Compose를 사용하면 host에 Node.js를 설치하지 않아도 된다.

```bash
docker compose --env-file .env.dev.local -f compose.dev.yaml --profile app up web
```

Node.js 24가 이미 있는 환경에서는 npm을 직접 사용할 수 있다.

```bash
cd frontend
npm ci
npm run dev
```

host에서 직접 실행한 Vite development server는 `127.0.0.1:5173`에 bind한다. Compose 내부에서는 container network를 위해 모든 interface를 수신하지만 host 공개 port는 `127.0.0.1:5173`으로 제한한다. `BACKEND_ORIGIN`은 development proxy의 server-side target이며 browser bundle에 secret을 넣지 않는다. 예시는 `.env.example`에 있다.

## 검증

```bash
npm run lint
npm run typecheck
npm run test:run
npm run build
```

repository root에서는 `./scripts/verify-frontend.sh`가 같은 순서를 실행하며 Node.js 24가 없으면 격리된 verification container를 사용한다.

`App.test.tsx`는 기본 화면의 제목, Foundation 상태, Backend/Frontend 기준이 렌더링되는지 확인한다. 인증, 업무 data 조회, PWA는 후속 Slice 범위다.
