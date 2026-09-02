import { type FormEvent, useEffect, useMemo, useState } from 'react'
import {
  type BudgetCategory,
  type BudgetInput,
  type BudgetOwner,
  type BudgetScope,
  type Category,
  type CurrentHousehold,
  LedgerApiError,
  createBudget,
  deleteBudget,
  updateBudget,
} from './ledgerApi.ts'

export type BudgetEditTarget = {
  budgetId: number | null
  version: number | null
  month: string
  scope: BudgetScope
  owner: BudgetOwner | null
  category: BudgetCategory | null
  amount: number | null
}

function scopeValue(target: BudgetEditTarget) {
  if (target.scope === 'PERSONAL' && target.owner) {
    return `PERSONAL:${target.owner.memberId}`
  }
  return target.scope
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) {
    if (error.code === 'BUDGET_DUPLICATE') {
      return '같은 월·범위·Category의 예산이 이미 있어요.'
    }
    if (error.code === 'BUDGET_VERSION_CONFLICT') {
      return '다른 변경이 먼저 저장됐어요. 화면을 새로 확인해 주세요.'
    }
    return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return '예산을 저장하지 못했습니다.'
}

function targetCopy(target: BudgetEditTarget) {
  const scope = target.scope === 'HOUSEHOLD'
    ? '가계 전체 한도'
    : target.scope === 'SHARED'
      ? '공동'
      : target.owner?.displayName ?? '개인'
  const category = target.category?.name ?? '전체 Category'
  const [year, month] = target.month.split('-').map(Number)
  return `${year}년 ${month}월 · ${scope} · ${category}`
}

export function BudgetSheet({
  target,
  household,
  categories,
  onChanged,
  onRequestClose,
}: {
  target: BudgetEditTarget
  household: CurrentHousehold
  categories: Category[]
  onChanged: () => void | Promise<void>
  onRequestClose: () => void
}) {
  const [month, setMonth] = useState(target.month)
  const [selectedScope, setSelectedScope] = useState(scopeValue(target))
  const [categoryId, setCategoryId] = useState(target.category?.id.toString() ?? '')
  const [amount, setAmount] = useState(target.amount?.toString() ?? '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const expenseCategories = useMemo(() => categories.filter(
    (category) => category.type === 'EXPENSE' && !category.archived,
  ), [categories])
  const selectedArchivedCategory = target.category?.archived === true
    && categoryId === target.category.id.toString()

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onRequestClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onRequestClose, pending])

  function input(): BudgetInput {
    const [scope, memberId] = selectedScope.split(':')
    return {
      month,
      scope: scope as BudgetScope,
      ownerMemberId: scope === 'PERSONAL' ? Number(memberId) : null,
      categoryId: categoryId ? Number(categoryId) : null,
      amount: Number(amount),
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      if (target.budgetId !== null && target.version !== null) {
        await updateBudget(target.budgetId, target.version, input())
      } else {
        await createBudget(input())
      }
      await onChanged()
      onRequestClose()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  async function remove() {
    if (target.budgetId === null || target.version === null) return
    setPending(true)
    setError(null)
    try {
      await deleteBudget(target.budgetId, target.version)
      await onChanged()
      onRequestClose()
    } catch (deleteError) {
      setError(errorMessage(deleteError))
      setConfirmingDelete(false)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pending) onRequestClose()
    }}>
      <section
        className="bottom-sheet budget-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="budget-sheet-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Monthly Budget</p>
            <h2 id="budget-sheet-title">
              {target.budgetId === null ? '예산 추가' : '예산 수정'}
            </h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="예산 입력 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>

        <form className="entry-form" onSubmit={submit}>
          <label>
            월
            <input
              required
              type="month"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            />
          </label>
          <label>
            범위
            <select
              value={selectedScope}
              aria-label="범위"
              aria-describedby={selectedScope === 'HOUSEHOLD'
                ? 'household-budget-scope-hint'
                : undefined}
              onChange={(event) => setSelectedScope(event.target.value)}
            >
              <option value="HOUSEHOLD">가계 전체 한도</option>
              {household.members.map((member) => (
                <option key={member.memberId} value={`PERSONAL:${member.memberId}`}>
                  {member.displayName}
                </option>
              ))}
              <option value="SHARED">공동</option>
            </select>
            {selectedScope === 'HOUSEHOLD' && (
              <span id="household-budget-scope-hint" className="field-hint">
                개인 예산 합계가 아니라, 개인·공동 지출 전체에 적용할 별도 월 한도예요.
              </span>
            )}
          </label>
          <label>
            Category
            <select value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
              <option value="">전체 Category</option>
              {target.category?.archived && (
                <option value={target.category.id}>
                  {target.category.name} · 보관됨
                </option>
              )}
              {expenseCategories
                .filter((category) => category.id !== target.category?.id)
                .map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              {!target.category?.archived && target.category && (
                <option value={target.category.id}>{target.category.name}</option>
              )}
            </select>
          </label>
          {selectedArchivedCategory && (
            <p className="field-hint" role="status">
              보관된 Category는 새로 저장할 수 없습니다. 다른 Category나 전체를 선택하거나 예산을 삭제해 주세요.
            </p>
          )}
          <label className="amount-field">
            예산 금액
            <span>
              <input
                required
                autoFocus
                aria-label="예산 금액"
                min="0"
                inputMode="numeric"
                type="number"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              /> 원
            </span>
          </label>
          <button
            className="primary-button sheet-submit"
            type="submit"
            disabled={pending || selectedArchivedCategory}
          >
            {pending ? '저장 중…' : '예산 저장'}
          </button>
        </form>

        {target.budgetId !== null && !confirmingDelete && (
          <button
            className="danger-outline-button"
            type="button"
            disabled={pending}
            onClick={() => setConfirmingDelete(true)}
          >
            예산 삭제
          </button>
        )}
        {confirmingDelete && (
          <div className="budget-delete-confirm" role="alert">
            <strong>{targetCopy(target)} 예산만 삭제할까요?</strong>
            <p>거래와 사용액은 그대로 유지됩니다.</p>
            <div>
              <button type="button" disabled={pending} onClick={() => setConfirmingDelete(false)}>
                취소
              </button>
              <button type="button" disabled={pending} onClick={() => void remove()}>
                {pending ? '삭제 중…' : '삭제 확인'}
              </button>
            </div>
          </div>
        )}
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>
  )
}
