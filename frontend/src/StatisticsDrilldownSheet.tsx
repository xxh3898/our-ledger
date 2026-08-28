import { useEffect, useRef, useState } from 'react'
import {
  type CalendarFilter,
  type LedgerTransaction,
  LedgerApiError,
  type SavingsActivity,
  loadSavingsActivities,
  loadStatisticsTransactions,
} from './ledgerApi.ts'

export type StatisticsDrilldownTarget =
  | {
    kind: 'transactions'
    title: string
    type: 'INCOME' | 'EXPENSE'
    filter: CalendarFilter
    categoryId?: number
    accountId?: number
  }
  | {
    kind: 'savings'
    title: string
  }

type State =
  | { status: 'loading' }
  | { status: 'ready'; transactions: LedgerTransaction[]; activities: SavingsActivity[] }
  | { status: 'error'; message: string }

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '통계 원장 내역을 불러오지 못했습니다.'
}

function occurredOn(occurredAt: string, timezone: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: timezone,
    month: 'long',
    day: 'numeric',
  }).format(new Date(occurredAt))
}

export function StatisticsDrilldownSheet({
  range,
  timezone,
  target,
  onRequestClose,
}: {
  range: { from: string; to: string }
  timezone: string
  target: StatisticsDrilldownTarget
  onRequestClose: () => void
}) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [revision, setRevision] = useState(0)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeButtonRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onRequestClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onRequestClose])

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    const promise = target.kind === 'savings'
      ? loadSavingsActivities(range, controller.signal)
        .then((activities) => ({ transactions: [], activities }))
      : loadStatisticsTransactions(
        range,
        target.filter,
        {
          type: target.type,
          categoryId: target.categoryId,
          accountId: target.accountId,
        },
        controller.signal,
      ).then((transactions) => ({ transactions, activities: [] }))
    void promise
      .then((data) => setState({ status: 'ready', ...data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [range, revision, target])

  const hasItems = state.status === 'ready'
    && (state.transactions.length > 0 || state.activities.length > 0)
  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onRequestClose()
    }}>
      <section
        className="bottom-sheet statistics-drilldown-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="statistics-drilldown-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">{range.from} ~ {range.to}</p>
            <h2 id="statistics-drilldown-title">{target.title}</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            aria-label="통계 원장 내역 닫기"
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>

        {state.status === 'loading' && <p role="status">원장 내역을 불러오고 있어요.</p>}
        {state.status === 'error' && (
          <div className="inline-error" role="alert">
            <span>{state.message}</span>
            <button type="button" onClick={() => setRevision((value) => value + 1)}>
              다시 불러오기
            </button>
          </div>
        )}
        {state.status === 'ready' && !hasItems && (
          <p className="list-state">이 조건의 원장 내역이 없어요.</p>
        )}
        {state.status === 'ready' && state.transactions.length > 0 && (
          <ul className="statistics-transaction-list">
            {state.transactions.map((transaction) => {
              const refund = transaction.adjustmentType === 'REFUND'
              const income = transaction.type === 'INCOME'
              return (
                <li key={transaction.id}>
                  <div>
                    <strong>
                      {transaction.category?.name ?? (income ? '수입' : '지출')}
                      {refund ? ' 환불' : ''}
                    </strong>
                    <span>
                      {occurredOn(transaction.occurredAt, timezone)}
                      {transaction.scope === 'SHARED'
                        ? ' · 공동'
                        : transaction.owner
                          ? ` · ${transaction.owner.displayName}`
                          : ''}
                      {transaction.memo ? ` · ${transaction.memo}` : ''}
                    </span>
                  </div>
                  <b className={refund || income ? 'is-positive' : ''}>
                    {refund || income ? '+' : '−'}
                    {transaction.amount.toLocaleString('ko-KR')}원
                  </b>
                </li>
              )
            })}
          </ul>
        )}
        {state.status === 'ready' && state.activities.length > 0 && (
          <ul className="statistics-transaction-list">
            {state.activities.map((activity) => (
              <li key={activity.transactionId}>
                <div>
                  <strong>{activity.sourceAccount.name} → {activity.destinationAccount.name}</strong>
                  <span>
                    {occurredOn(activity.occurredAt, timezone)}
                    {activity.memo ? ` · ${activity.memo}` : ''}
                  </span>
                </div>
                <b className={activity.savingsImpactAmount >= 0 ? 'is-positive' : ''}>
                  {activity.savingsImpactAmount >= 0 ? '+' : '−'}
                  {Math.abs(activity.savingsImpactAmount).toLocaleString('ko-KR')}원
                </b>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
