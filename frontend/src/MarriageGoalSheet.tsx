import { type FormEvent, useEffect, useState } from 'react'
import {
  type MarriageGoalView,
  LedgerApiError,
  createMarriageGoal,
  updateMarriageGoal,
} from './ledgerApi.ts'

function goalErrorMessage(error: unknown) {
  if (error instanceof LedgerApiError) {
    if (error.code === 'GOAL_ALREADY_EXISTS') {
      return '결혼자금 목표가 이미 있어요. 최신 화면을 다시 확인해 주세요.'
    }
    if (error.code === 'GOAL_VERSION_CONFLICT') {
      return '다른 변경이 먼저 저장됐어요. 최신 Goal을 다시 확인해 주세요.'
    }
    return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return 'Goal을 저장하지 못했습니다.'
}

export function MarriageGoalSheet({
  goal,
  onSaved,
  onRequestClose,
}: {
  goal: NonNullable<MarriageGoalView['goal']> | null
  onSaved: (view: MarriageGoalView) => void
  onRequestClose: () => void
}) {
  const [name, setName] = useState(goal?.name ?? '')
  const [targetAmount, setTargetAmount] = useState(goal?.targetAmount.toString() ?? '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onRequestClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onRequestClose, pending])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const input = { name: name.trim(), targetAmount: Number(targetAmount) }
      const view = goal
        ? await updateMarriageGoal(goal.version, input)
        : await createMarriageGoal(input)
      onSaved(view)
      onRequestClose()
    } catch (submitError) {
      setError(goalErrorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pending) onRequestClose()
    }}>
      <section
        className="bottom-sheet goal-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="goal-sheet-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Marriage Goal</p>
            <h2 id="goal-sheet-title">{goal ? '결혼자금 Goal 수정' : '결혼자금 목표 만들기'}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Goal 입력 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <form className="compact-form goal-form" onSubmit={submit}>
          <label>
            목표 이름
            <input
              required
              autoFocus
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="amount-field">
            목표 금액
            <span>
              <input
                required
                aria-label="목표 금액"
                min="1"
                inputMode="numeric"
                type="number"
                value={targetAmount}
                onChange={(event) => setTargetAmount(event.target.value)}
              /> 원
            </span>
          </label>
          <p className="field-hint">
            현재 금액은 별도 기여금이 아니라 연결한 실제 Account 잔액으로 계산해요.
          </p>
          <button className="primary-button sheet-submit" type="submit" disabled={pending}>
            {pending ? '저장 중…' : 'Goal 저장'}
          </button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>
  )
}
