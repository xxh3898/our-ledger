import type { MarriageGoalView } from './ledgerApi.ts'

export type GoalViewState =
  | { status: 'loading' }
  | { status: 'ready'; data: MarriageGoalView }
  | { status: 'error'; message: string }

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

export function MarriageGoalCard({
  state,
  onRetry,
  onOpen,
  onCreate,
}: {
  state: GoalViewState
  onRetry: () => void
  onOpen: (opener: HTMLElement) => void
  onCreate: (opener: HTMLElement) => void
}) {
  return (
    <section
      className="goal-shell goal-card"
      aria-labelledby="goal-title"
      aria-busy={state.status === 'loading'}
    >
      {state.status === 'loading' && (
        <div className="goal-card-status" role="status">
          <span className="goal-paw" aria-hidden="true">♡</span>
          <span>결혼자금 Goal을 계산하고 있어요.</span>
        </div>
      )}
      {state.status === 'error' && (
        <div className="inline-error" role="alert">
          <span>{state.message}</span>
          <button type="button" onClick={onRetry}>다시 불러오기</button>
        </div>
      )}
      {state.status === 'ready' && state.data.goal === null && (
        <div className="goal-empty-card">
          <span className="goal-paw" aria-hidden="true">♡</span>
          <div>
            <p className="section-kicker">Marriage Goal</p>
            <h2 id="goal-title">둘의 결혼자금 목표를 만들어 보세요</h2>
            <p>실제 저축 Account를 연결해 함께 진행률을 확인할 수 있어요.</p>
            <button type="button" onClick={(event) => onCreate(event.currentTarget)}>
              결혼자금 목표 만들기
            </button>
          </div>
        </div>
      )}
      {state.status === 'ready' && state.data.goal && (() => {
        const goal = state.data.goal
        const visualRate = Math.min(Math.max(goal.achievementRate, 0), 100)
        return (
          <button
            className="goal-card-button"
            type="button"
            onClick={(event) => onOpen(event.currentTarget)}
          >
            <span className="goal-card-heading">
              <span>
                <span className="section-kicker">Marriage Goal</span>
                <strong id="goal-title">{goal.name}</strong>
              </span>
              <b>{goal.achievementRate.toFixed(1)}%</b>
            </span>
            <span className="goal-card-amount">
              {formatWon(goal.currentAmount)} <small>/ {formatWon(goal.targetAmount)}</small>
            </span>
            <span
              className="goal-progress"
              role="progressbar"
              aria-label="결혼자금 Goal 달성률"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={visualRate}
            >
              <span style={{ width: `${visualRate}%` }} />
            </span>
            <span className="goal-card-footer">
              <span>이번 달 {goal.thisMonthSavingsAmount >= 0 ? '+' : '−'}
                {formatWon(Math.abs(goal.thisMonthSavingsAmount))}</span>
              <span>상세 보기 →</span>
            </span>
            {goal.linkedAccounts.length === 0 && (
              <span className="goal-account-empty">저축 Account를 연결해 주세요.</span>
            )}
          </button>
        )
      })()}
    </section>
  )
}
