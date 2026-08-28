import { useEffect, useRef, useState } from 'react'
import {
  type BudgetCategory,
  type BudgetOwner,
  type BudgetScope,
  type LedgerTransaction,
  LedgerApiError,
  loadBudgetTransactions,
} from './ledgerApi.ts'

export type BudgetDrilldownTarget = {
  scope: BudgetScope
  owner: BudgetOwner | null
  category: BudgetCategory | null
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '사용 내역을 불러오지 못했습니다.'
}

function title(target: BudgetDrilldownTarget) {
  const scope = target.scope === 'HOUSEHOLD'
    ? '우리 전체'
    : target.scope === 'SHARED'
      ? '공동'
      : target.owner?.displayName ?? '개인'
  return `${scope}${target.category ? ` · ${target.category.name}` : ''}`
}

function occurredOn(occurredAt: string, timezone: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: timezone,
    month: 'long',
    day: 'numeric',
  }).format(new Date(occurredAt))
}

export function BudgetDrilldownSheet({
  month,
  timezone,
  target,
  onRequestClose,
}: {
  month: string
  timezone: string
  target: BudgetDrilldownTarget
  onRequestClose: () => void
}) {
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'ready'; data: LedgerTransaction[] }
    | { status: 'error'; message: string }
  >({ status: 'loading' })
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
    void loadBudgetTransactions(
      month,
      target.scope,
      target.owner?.memberId ?? null,
      target.category?.id ?? null,
      controller.signal,
    )
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [month, revision, target])

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onRequestClose()
    }}>
      <section
        className="bottom-sheet budget-drilldown-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="budget-drilldown-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">{month} 사용 내역</p>
            <h2 id="budget-drilldown-title">{title(target)}</h2>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button"
            type="button"
            aria-label="예산 사용 내역 닫기"
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        {state.status === 'loading' && <p role="status">거래를 불러오고 있어요.</p>}
        {state.status === 'error' && (
          <div className="inline-error" role="alert">
            <span>{state.message}</span>
            <button type="button" onClick={() => setRevision((current) => current + 1)}>
              다시 불러오기
            </button>
          </div>
        )}
        {state.status === 'ready' && state.data.length === 0 && (
          <p className="list-state">이 조건의 지출·환불 내역이 없어요.</p>
        )}
        {state.status === 'ready' && state.data.length > 0 && (
          <ul className="budget-transaction-list">
            {state.data.map((transaction) => {
              const refund = transaction.adjustmentType === 'REFUND'
              return (
                <li key={transaction.id}>
                  <div>
                    <strong>
                      {transaction.category?.name ?? '지출'}{refund ? ' 환불' : ''}
                    </strong>
                    <span>
                      {occurredOn(transaction.occurredAt, timezone)} · {transaction.scope === 'SHARED'
                        ? '공동'
                        : transaction.owner?.displayName ?? '개인'}
                      {transaction.memo ? ` · ${transaction.memo}` : ''}
                    </span>
                  </div>
                  <b className={refund ? 'is-refund' : ''}>
                    {refund ? '+' : '−'}{transaction.amount.toLocaleString('ko-KR')}원
                  </b>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
