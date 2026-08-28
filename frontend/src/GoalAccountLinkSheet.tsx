import { type FormEvent, useEffect, useRef, useState } from 'react'
import {
  type MarriageGoalView,
  LedgerApiError,
  linkMarriageGoalAccount,
} from './ledgerApi.ts'

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function linkErrorMessage(error: unknown) {
  if (error instanceof LedgerApiError) {
    if (error.code === 'GOAL_ACCOUNT_ALREADY_ASSIGNED') {
      return '이 Account는 다른 Goal에 먼저 연결됐어요. 목록을 새로 확인해 주세요.'
    }
    if (error.code === 'GOAL_ACCOUNT_NOT_ELIGIBLE') {
      return '현재 연결할 수 없는 Account예요. 활성 저축 ASSET 상태를 확인해 주세요.'
    }
    return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return 'Account를 연결하지 못했습니다.'
}

export function GoalAccountLinkSheet({
  accounts,
  onSaved,
  onRequestClose,
}: {
  accounts: MarriageGoalView['eligibleAccounts']
  onSaved: (view: MarriageGoalView) => void
  onRequestClose: () => void
}) {
  const [accountId, setAccountId] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (accounts.length > 0) {
      document.querySelector<HTMLInputElement>('input[name="goal-account"]')?.focus()
    } else {
      closeButtonRef.current?.focus()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onRequestClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [accounts.length, onRequestClose, pending])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending || !accountId) return
    setPending(true)
    setError(null)
    try {
      const view = await linkMarriageGoalAccount(Number(accountId))
      onSaved(view)
      onRequestClose()
    } catch (submitError) {
      setError(linkErrorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pending) onRequestClose()
    }}>
      <section
        className="bottom-sheet goal-link-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="goal-link-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Actual Account</p>
            <h2 id="goal-link-title">저축 Account 연결</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            aria-label="Account 연결 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        {accounts.length === 0 ? (
          <p className="list-state">연결할 수 있는 활성 저축 Account가 없어요.</p>
        ) : (
          <form className="goal-link-form" onSubmit={submit}>
            <fieldset>
              <legend>연결할 Account</legend>
              {accounts.map((account) => (
                <label key={account.id} className="goal-account-choice">
                  <input
                    required
                    type="radio"
                    name="goal-account"
                    value={account.id}
                    checked={accountId === account.id.toString()}
                    onChange={(event) => setAccountId(event.target.value)}
                  />
                  <span>
                    <strong>{account.name}</strong>
                    <small>
                      {account.ownership === 'SHARED'
                        ? '공동'
                        : account.owner?.displayName ?? '개인'} · {formatWon(account.currentBalance)}
                    </small>
                  </span>
                </label>
              ))}
            </fieldset>
            <button
              className="primary-button sheet-submit"
              type="submit"
              disabled={pending || !accountId}
            >
              {pending ? '연결 중…' : '선택한 Account 연결'}
            </button>
          </form>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>
  )
}
