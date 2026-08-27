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

host에서 직접 실행한 Vite development server는 `127.0.0.1:5173`에 bind한다. Compose 내부에서는 container network를 위해 모든 interface를 수신하지만 host 공개 port는 `127.0.0.1:5173`으로 제한한다. `BACKEND_ORIGIN`은 development proxy의 server-side target이며 browser bundle에 secret을 넣지 않는다.

local에서는 `OUR_LEDGER_LOCAL_IDENTITY_EMAIL`이 Vite proxy의 server-side 설정으로만 사용되고 `/api` 요청에 `X-Our-Ledger-Local-Identity`를 추가한다. `VITE_` prefix가 아니므로 browser bundle에 포함되지 않는다. backend의 local/test filter도 해당 identity를 내부 User와 Household membership에 다시 매핑한다. 예시는 root `.env.example`의 가짜 `example.test` 값이다.

## 검증

```bash
npm run lint
npm run typecheck
npm run test:run
npm run build
```

repository root에서는 `./scripts/verify-frontend.sh`가 같은 순서를 실행하며 Node.js 24가 없으면 격리된 verification container를 사용한다.

`App.test.tsx`는 `/api/v1/me`의 loading, 정상 User/Household/role, 401 인증 필요, 403 미등록 User 상태를 검증한다. 애플리케이션 자체 로그인·OTP 화면은 제공하지 않는다.
