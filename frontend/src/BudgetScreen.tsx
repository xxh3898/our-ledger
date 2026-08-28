import { useCallback, useEffect, useRef, useState } from 'react'
import { BudgetDrilldownSheet, type BudgetDrilldownTarget } from './BudgetDrilldownSheet.tsx'
import { BudgetSheet, type BudgetEditTarget } from './BudgetSheet.tsx'
import {
  type BudgetCategory,
  type BudgetMonth,
  type BudgetOwner,
  type BudgetScope,
  type Category,
  type CurrentHousehold,
  LedgerApiError,
  loadBudgetMonth,
} from './ledgerApi.ts'

type BudgetScopeItem = BudgetMonth['scopes'][number]
type CategoryBudgetItem = BudgetMonth['categories'][number]
type FocusReturnTarget = {
  element: HTMLElement
  key: string | null
}

function focusReturnTarget(element: HTMLElement): FocusReturnTarget {
  return {
    element,
    key: element.dataset.budgetFocusKey ?? null,
  }
}

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '예산 정보를 불러오지 못했습니다.'
}

function scopeLabel(scope: BudgetScope, owner: BudgetOwner | null) {
  if (scope === 'HOUSEHOLD') return '우리 전체'
  if (scope === 'SHARED') return '공동'
  return owner?.displayName ?? '개인'
}

function editTarget(
  month: string,
  item: BudgetScopeItem | CategoryBudgetItem,
  category: BudgetCategory | null,
): BudgetEditTarget {
  return {
    budgetId: item.budgetId,
    version: item.version,
    month,
    scope: item.scope,
    owner: item.owner,
    category,
    amount: item.budgetAmount,
  }
}

function Usage({
  budgetAmount,
  spentAmount,
  remainingAmount,
  exceeded,
}: {
  budgetAmount: number | null
  spentAmount: number
  remainingAmount: number | null
  exceeded: boolean
}) {
  if (budgetAmount === null) {
    return (
      <div className="budget-values">
        <strong>예산 미설정</strong>
        <span>이번 달 사용 {formatWon(spentAmount)}</span>
      </div>
    )
  }
  const usageRate = budgetAmount > 0
    ? Math.round((spentAmount / budgetAmount) * 100)
    : null
  const progressWidth = usageRate === null ? 0 : Math.min(100, Math.max(0, usageRate))
  return (
    <div className="budget-values">
      <dl>
        <div><dt>예산</dt><dd>{formatWon(budgetAmount)}</dd></div>
        <div><dt>사용</dt><dd>{formatWon(spentAmount)}</dd></div>
        <div><dt>남음</dt><dd>{formatWon(remainingAmount ?? 0)}</dd></div>
      </dl>
      {usageRate !== null && (
        <>
          <div className="budget-progress" aria-hidden="true">
            <span style={{ width: `${progressWidth}%` }} />
          </div>
          <span className="budget-rate">사용률 {usageRate}%</span>
        </>
      )}
      {budgetAmount === 0 && spentAmount === 0 && <span>0원 예산을 설정했어요.</span>}
      {budgetAmount === 0 && spentAmount > 0 && (
        <strong className="budget-overrun">0원 예산을 초과했어요.</strong>
      )}
      {exceeded && budgetAmount > 0 && (
        <strong className="budget-overrun">
          예산을 {formatWon(Math.abs(remainingAmount ?? 0))} 초과했어요.
        </strong>
      )}
    </div>
  )
}

function BudgetCard({
  month,
  item,
  onEdit,
  onDrilldown,
}: {
  month: string
  item: BudgetScopeItem
  onEdit: (target: BudgetEditTarget, opener: HTMLElement) => void
  onDrilldown: (target: BudgetDrilldownTarget, opener: HTMLElement) => void
}) {
  const label = scopeLabel(item.scope, item.owner)
  return (
    <article className={`budget-card${item.exceeded ? ' is-over' : ''}`}>
      <header>
        <div>
          <p className="section-kicker">{item.scope}</p>
          <h3>{label}</h3>
        </div>
        <button
          type="button"
          data-budget-focus-key={`scope:${item.scope}:${item.owner?.memberId ?? 'none'}:edit`}
          onClick={(event) => onEdit(editTarget(month, item, null), event.currentTarget)}
        >
          {item.budgetId === null ? '설정' : '수정'}
        </button>
      </header>
      <Usage
        budgetAmount={item.budgetAmount}
        spentAmount={item.spentAmount}
        remainingAmount={item.remainingAmount}
        exceeded={item.exceeded}
      />
      <button
        className="budget-spending-link"
        type="button"
        data-budget-focus-key={`scope:${item.scope}:${item.owner?.memberId ?? 'none'}:drilldown`}
        onClick={(event) => onDrilldown(
          { scope: item.scope, owner: item.owner, category: null },
          event.currentTarget,
        )}
      >
        {label} 사용 내역 보기
      </button>
    </article>
  )
}

export function BudgetScreen({
  month,
  household,
  categories,
  revision,
  onMoveMonth,
  onChanged,
}: {
  month: string
  household: CurrentHousehold
  categories: Category[]
  revision: number
  onMoveMonth: (offset: number) => void
  onChanged: () => void
}) {
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'ready'; data: BudgetMonth }
    | { status: 'error'; message: string }
  >({ status: 'loading' })
  const [retryRevision, setRetryRevision] = useState(0)
  const [editing, setEditing] = useState<BudgetEditTarget | null>(null)
  const [drilldown, setDrilldown] = useState<BudgetDrilldownTarget | null>(null)
  const editingOpenerRef = useRef<FocusReturnTarget | null>(null)
  const drilldownOpenerRef = useRef<FocusReturnTarget | null>(null)
  const pendingFocusRef = useRef<FocusReturnTarget | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    void loadBudgetMonth(month, controller.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [month, retryRevision, revision])

  useEffect(() => {
    if (editing || drilldown || !pendingFocusRef.current) return
    const timeout = window.setTimeout(() => {
      const pending = pendingFocusRef.current
      if (!pending) return
      const replacement = pending.key
        ? document.querySelector<HTMLElement>(`[data-budget-focus-key="${pending.key}"]`)
        : null
      const target = pending.element.isConnected
        ? pending.element
        : replacement ?? document.querySelector<HTMLElement>(
          '[data-budget-focus-key="budget:add"]',
        )
      if (target) {
        target.focus()
        pendingFocusRef.current = null
      }
    }, 0)
    return () => window.clearTimeout(timeout)
  }, [drilldown, editing, state.status])

  function openEditing(target: BudgetEditTarget, opener: HTMLElement) {
    editingOpenerRef.current = focusReturnTarget(opener)
    setEditing(target)
  }

  function openDrilldown(target: BudgetDrilldownTarget, opener: HTMLElement) {
    drilldownOpenerRef.current = focusReturnTarget(opener)
    setDrilldown(target)
  }

  const closeEditing = useCallback(() => {
    pendingFocusRef.current = editingOpenerRef.current
    editingOpenerRef.current = null
    setEditing(null)
  }, [])

  const closeDrilldown = useCallback(() => {
    pendingFocusRef.current = drilldownOpenerRef.current
    drilldownOpenerRef.current = null
    setDrilldown(null)
  }, [])

  const [year, monthNumber] = month.split('-').map(Number)
  return (
    <>
      <section className="budget-heading" aria-labelledby="budget-title">
        <p className="section-kicker">Slice 5 · Monthly Budget</p>
        <h2 id="budget-title">예산</h2>
        <p>거래 원장에서 계산한 이번 달 사용액과 남은 금액을 함께 봅니다.</p>
      </section>
      <div className="month-navigation budget-month-navigation">
        <button type="button" aria-label="예산 이전 달" onClick={() => onMoveMonth(-1)}>‹</button>
        <h2>{year}년 {monthNumber}월</h2>
        <button type="button" aria-label="예산 다음 달" onClick={() => onMoveMonth(1)}>›</button>
      </div>

      {state.status === 'loading' && (
        <p className="budget-page-state" role="status">월 예산과 사용액을 계산하고 있어요.</p>
      )}
      {state.status === 'error' && (
        <div className="inline-error budget-page-state" role="alert">
          <span>{state.message}</span>
          <button type="button" onClick={() => setRetryRevision((current) => current + 1)}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.status === 'ready' && (
        <>
          <section className="budget-scope-section" aria-labelledby="scope-budget-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">기본 범위</p>
                <h2 id="scope-budget-title">우리의 월 예산</h2>
              </div>
            </div>
            <div className="budget-card-grid">
              {state.data.scopes.map((item) => (
                <BudgetCard
                  key={`${item.scope}:${item.owner?.memberId ?? ''}`}
                  month={month}
                  item={item}
                  onEdit={openEditing}
                  onDrilldown={openDrilldown}
                />
              ))}
            </div>
          </section>

          <section className="category-budget-section" aria-labelledby="category-budget-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">Category Budget</p>
                <h2 id="category-budget-title">Category 예산</h2>
              </div>
              <span className="count-badge">{state.data.categories.length}</span>
            </div>
            {state.data.categories.length === 0 && (
              <p className="list-state">설정한 Category 예산이 아직 없어요.</p>
            )}
            {state.data.categories.length > 0 && (
              <ul className="category-budget-list">
                {state.data.categories.map((item) => (
                  <li key={item.budgetId} className={item.exceeded ? 'is-over' : ''}>
                    <div className="category-budget-copy">
                      <strong>
                        {item.category.name}
                        {item.category.archived && <small>보관됨</small>}
                      </strong>
                      <span>{scopeLabel(item.scope, item.owner)}</span>
                    </div>
                    <Usage
                      budgetAmount={item.budgetAmount}
                      spentAmount={item.spentAmount}
                      remainingAmount={item.remainingAmount}
                      exceeded={item.exceeded}
                    />
                    <div className="category-budget-actions">
                      <button
                        type="button"
                        data-budget-focus-key={`category:${item.budgetId}:drilldown`}
                        onClick={(event) => openDrilldown({
                          scope: item.scope,
                          owner: item.owner,
                          category: item.category,
                        }, event.currentTarget)}
                      >
                        사용 내역
                      </button>
                      <button
                        type="button"
                        data-budget-focus-key={`category:${item.budgetId}:edit`}
                        onClick={(event) => openEditing(
                          editTarget(month, item, item.category),
                          event.currentTarget,
                        )}
                      >
                        수정
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <button
            className="primary-button add-budget-button"
            type="button"
            data-budget-focus-key="budget:add"
            onClick={(event) => openEditing({
              budgetId: null,
              version: null,
              month,
              scope: 'HOUSEHOLD',
              owner: null,
              category: null,
              amount: null,
            }, event.currentTarget)}
          >
            + 예산 추가
          </button>
        </>
      )}

      {editing && (
        <BudgetSheet
          key={`${editing.budgetId ?? 'new'}:${editing.scope}:${editing.category?.id ?? ''}`}
          target={editing}
          household={household}
          categories={categories}
          onChanged={onChanged}
          onRequestClose={closeEditing}
        />
      )}
      {drilldown && (
        <BudgetDrilldownSheet
          month={month}
          timezone={household.timezone}
          target={drilldown}
          onRequestClose={closeDrilldown}
        />
      )}
    </>
  )
}
