import { useState } from 'react'
import type { GoalViewState } from './MarriageGoalCard.tsx'
import type { MarriageGoalView } from './ledgerApi.ts'

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function monthLabel(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  return `${year}년 ${monthNumber}월`
}

function projectionCopy(
  status: 'ACHIEVED' | 'INSUFFICIENT_HISTORY' | 'NON_POSITIVE_AVERAGE' | 'PROJECTED',
  month: string | null,
) {
  if (status === 'ACHIEVED') return '목표를 달성했어요.'
  if (status === 'INSUFFICIENT_HISTORY') return '완료된 3개월 기록이 쌓이면 예상 월을 보여 드려요.'
  if (status === 'NON_POSITIVE_AVERAGE') return '최근 월평균 순저축이 0원 이하라 예상할 수 없어요.'
  return month ? `${monthLabel(month)} 예상` : '예상 월을 계산할 수 없어요.'
}

function TrendChart({
  trend,
}: {
  trend: NonNullable<MarriageGoalView['goal']>['monthlyTrend']
}) {
  const values = trend.map((item) => item.savingsAmount)
  const minimum = Math.min(...values, 0)
  const maximum = Math.max(...values, 0)
  const range = maximum - minimum || 1
  const points = values.map((value, index) => {
    const x = 8 + (index * 84) / Math.max(values.length - 1, 1)
    const y = 54 - ((value - minimum) / range) * 44
    return `${x},${y}`
  }).join(' ')
  return (
    <div className="goal-trend">
      <svg viewBox="0 0 100 62" role="img" aria-labelledby="goal-trend-title">
        <title id="goal-trend-title">최근 6개월 결혼자금 순저축 추이</title>
        <line x1="8" y1="54" x2="92" y2="54" />
        <polyline points={points} />
        {points.split(' ').map((point, index) => {
          const [cx, cy] = point.split(',')
          return <circle key={trend[index].month} cx={cx} cy={cy} r="2" />
        })}
      </svg>
      <table>
        <caption>최근 6개월 월별 순저축</caption>
        <thead><tr><th>월</th><th>순저축</th></tr></thead>
        <tbody>
          {trend.map((item) => (
            <tr key={item.month}>
              <th scope="row">{monthLabel(item.month)}</th>
              <td>{formatWon(item.savingsAmount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function MarriageGoalScreen({
  state,
  timezone,
  onBack,
  onRetry,
  onCreate,
  onEdit,
  onLink,
  onUnlink,
}: {
  state: GoalViewState
  timezone: string
  onBack: () => void
  onRetry: () => void
  onCreate: (opener: HTMLElement) => void
  onEdit: (opener: HTMLElement) => void
  onLink: (opener: HTMLElement) => void
  onUnlink: (accountId: number) => Promise<void>
}) {
  const [confirmingUnlink, setConfirmingUnlink] = useState<number | null>(null)
  const [unlinking, setUnlinking] = useState(false)
  const [unlinkError, setUnlinkError] = useState<string | null>(null)

  async function unlink(accountId: number) {
    if (unlinking) return
    setUnlinking(true)
    setUnlinkError(null)
    try {
      await onUnlink(accountId)
      setConfirmingUnlink(null)
    } catch (error) {
      setUnlinkError(error instanceof Error ? error.message : '연결을 해제하지 못했습니다.')
    } finally {
      setUnlinking(false)
    }
  }

  return (
    <section className="goal-screen" aria-labelledby="goal-screen-title">
      <header className="goal-screen-header">
        <button type="button" onClick={onBack}>← Calendar</button>
        <div>
          <p className="section-kicker">Marriage Goal</p>
          <h2 id="goal-screen-title">결혼자금</h2>
        </div>
      </header>
      {state.status === 'loading' && (
        <div className="goal-detail-state" role="status">Goal 지표를 다시 계산하고 있어요.</div>
      )}
      {state.status === 'error' && (
        <div className="inline-error" role="alert">
          <span>{state.message}</span>
          <button type="button" onClick={onRetry}>다시 불러오기</button>
        </div>
      )}
      {state.status === 'ready' && state.data.goal === null && (
        <div className="goal-detail-state">
          <strong>아직 결혼자금 Goal이 없어요.</strong>
          <button type="button" onClick={(event) => onCreate(event.currentTarget)}>
            결혼자금 목표 만들기
          </button>
        </div>
      )}
      {state.status === 'ready' && state.data.goal && (() => {
        const goal = state.data.goal
        const visualRate = Math.min(Math.max(goal.achievementRate, 0), 100)
        return (
          <div className="goal-detail-content">
            <section className="goal-detail-hero">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">Actual Ledger</p>
                  <h3>{goal.name}</h3>
                </div>
                <button type="button" onClick={(event) => onEdit(event.currentTarget)}>수정</button>
              </div>
              <strong>{formatWon(goal.currentAmount)}</strong>
              <span>/ {formatWon(goal.targetAmount)}</span>
              <div
                className="goal-progress"
                role="progressbar"
                aria-label="결혼자금 Goal 달성률"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={visualRate}
              >
                <span style={{ width: `${visualRate}%` }} />
              </div>
              <p>{goal.achievementRate.toFixed(1)}% · 남은 금액 {formatWon(goal.remainingAmount)}</p>
            </section>

            <section className="goal-metric-grid" aria-label="Goal 저축 지표">
              <article><span>이번 달 순저축</span><strong>{formatWon(goal.thisMonthSavingsAmount)}</strong></article>
              <article><span>최근 완료 3개월 평균</span><strong>
                {goal.recentAverageMonthlySavingsAmount === null
                  ? '표본 부족'
                  : formatWon(goal.recentAverageMonthlySavingsAmount)}
              </strong></article>
              <article className="goal-projection-card">
                <span>최근 속도 기준 예상</span>
                <strong>{projectionCopy(goal.projectionStatus, goal.expectedAchievementMonth)}</strong>
                <small>예상 월은 확정된 목표일이 아니에요.</small>
              </article>
            </section>

            <section className="goal-panel" aria-labelledby="goal-trend-heading">
              <h3 id="goal-trend-heading">월별 순저축 추이</h3>
              <TrendChart trend={goal.monthlyTrend} />
            </section>

            <section className="goal-panel" aria-labelledby="goal-accounts-heading">
              <div className="section-heading">
                <div>
                  <h3 id="goal-accounts-heading">연결 Account</h3>
                  <p>현재 잔액을 Goal 보유금으로 합산해요.</p>
                </div>
                <button type="button" onClick={(event) => onLink(event.currentTarget)}>계좌 연결</button>
              </div>
              {goal.linkedAccounts.length === 0 ? (
                <p className="list-state">저축 Account를 연결해 주세요.</p>
              ) : (
                <ul className="goal-account-list">
                  {goal.linkedAccounts.map((account) => (
                    <li key={account.id}>
                      <div>
                        <strong>{account.name}{account.archived && <span>보관됨</span>}</strong>
                        <small>{account.ownership === 'SHARED'
                          ? '공동'
                          : account.owner?.displayName ?? '개인'} · {formatWon(account.currentBalance)}</small>
                      </div>
                      {confirmingUnlink === account.id ? (
                        <div className="goal-unlink-confirm" role="alert">
                          <span>연결만 해제할까요?</span>
                          <button type="button" disabled={unlinking} onClick={() => setConfirmingUnlink(null)}>취소</button>
                          <button type="button" disabled={unlinking} onClick={() => void unlink(account.id)}>
                            {unlinking ? '해제 중…' : '해제 확인'}
                          </button>
                        </div>
                      ) : (
                        <button type="button" onClick={() => setConfirmingUnlink(account.id)}>연결 해제</button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {unlinkError && <p className="form-error" role="alert">{unlinkError}</p>}
            </section>

            <section className="goal-panel" aria-labelledby="goal-activity-heading">
              <h3 id="goal-activity-heading">최근 저축 활동</h3>
              {goal.recentSavingsActivities.length === 0 ? (
                <p className="list-state">연결 이후 Goal 안팎을 오간 Transfer가 없어요.</p>
              ) : (
                <ul className="goal-activity-list">
                  {goal.recentSavingsActivities.map((activity) => (
                    <li key={activity.transactionId}>
                      <div>
                        <strong>{activity.sourceAccount.name} → {activity.destinationAccount.name}
                          {activity.generatedFromRecurringId !== null && (
                            <span className="provenance-badge">반복</span>
                          )}
                        </strong>
                        <small>{new Intl.DateTimeFormat('ko-KR', {
                          timeZone: timezone,
                          month: 'long',
                          day: 'numeric',
                        }).format(new Date(activity.occurredAt))}{activity.memo ? ` · ${activity.memo}` : ''}</small>
                      </div>
                      <b className={activity.savingsImpactAmount < 0 ? 'is-negative' : ''}>
                        {activity.savingsImpactAmount > 0 ? '+' : '−'}
                        {formatWon(Math.abs(activity.savingsImpactAmount))}
                      </b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )
      })()}
    </section>
  )
}
