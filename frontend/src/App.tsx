import { useEffect, useState } from 'react'
import './App.css'

type CurrentUser = {
  userId: number
  email: string
  displayName: string
  householdId: number
  householdName: string
  role: 'OWNER' | 'MEMBER'
}

type ViewState =
  | { status: 'loading' }
  | { status: 'ready'; user: CurrentUser }
  | { status: 'authentication-required' }
  | { status: 'access-denied'; code?: string }
  | { status: 'error' }

async function loadCurrentUser(signal: AbortSignal): Promise<ViewState> {
  try {
    const response = await fetch('/api/v1/me', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })

    if (response.ok) {
      return { status: 'ready', user: (await response.json()) as CurrentUser }
    }
    if (response.status === 401) {
      return { status: 'authentication-required' }
    }
    if (response.status === 403) {
      const error = (await response.json().catch(() => ({}))) as { code?: string }
      return { status: 'access-denied', code: error.code }
    }
    return { status: 'error' }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    return { status: 'error' }
  }
}

function AccessState({ state }: { state: ViewState }) {
  if (state.status === 'loading') {
    return (
      <div className="identity-state" role="status">
        <span className="status-dot status-dot--loading" aria-hidden="true" />
        현재 사용자와 Household를 확인하고 있습니다.
      </div>
    )
  }

  if (state.status === 'authentication-required') {
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>인증이 필요합니다.</strong>
        <span>Cloudflare Access 인증 후 다시 열어 주세요.</span>
      </div>
    )
  }

  if (state.status === 'access-denied') {
    const isUnregistered = state.code === 'USER_NOT_REGISTERED'
    const isDisabled = state.code === 'USER_DISABLED'
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>
          {isUnregistered
            ? '등록된 사용자가 아닙니다.'
            : isDisabled
              ? '비활성화된 사용자입니다.'
              : 'Household 접근 권한이 없습니다.'}
        </strong>
        <span>내부 User와 Household membership을 확인해 주세요.</span>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>현재 정보를 불러오지 못했습니다.</strong>
        <span>잠시 뒤 다시 시도해 주세요.</span>
      </div>
    )
  }

  return (
    <article className="identity-card" aria-label="현재 사용자와 Household">
      <div className="avatar" aria-hidden="true">
        {state.user.displayName.slice(0, 1)}
      </div>
      <div className="identity-copy">
        <p>현재 사용자</p>
        <h2>{state.user.displayName}</h2>
        <span>{state.user.email}</span>
      </div>
      <dl>
        <div>
          <dt>Household</dt>
          <dd>{state.user.householdName}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{state.user.role}</dd>
        </div>
      </dl>
    </article>
  )
}

function App() {
  const [state, setState] = useState<ViewState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void loadCurrentUser(controller.signal)
      .then(setState)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error' })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">둘이 함께 쌓는 하나의 기록</p>
        <h1 id="page-title">우리의 장부</h1>
        <p className="hero-copy">
          검증된 사용자와 Household 경계 안에서 함께 재무 기록을 시작합니다.
        </p>
      </section>

      <section className="identity" aria-labelledby="identity-title">
        <div>
          <p className="section-kicker">Slice 1</p>
          <h2 id="identity-title">안전한 시작점</h2>
          <p className="section-copy">
            외부 인증과 내부 Household 권한을 각각 확인합니다.
          </p>
        </div>
        <AccessState state={state} />
      </section>
    </main>
  )
}

export default App
