import { type FormEvent, useEffect, useRef, useState } from 'react'
import { dateInTimeZone, noonInTimeZone } from './dateTime.ts'
import {
  type Account,
  type Category,
  type CurrentHousehold,
  type LedgerTransaction,
  LedgerApiError,
  createTransaction,
  updateTransaction,
} from './ledgerApi.ts'
import { entryByRole, isPrimaryAccountForType } from './transactionUtils.ts'

type TransactionFormState = {
  type: LedgerTransaction['type']
  amount: string
  scope: Exclude<LedgerTransaction['scope'], null>
  ownerMemberId: string
  payerMemberId: string
  categoryId: string
  accountId: string
  sourceAccountId: string
  destinationAccountId: string
  occurredOn: string
  memo: string
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '요청을 처리하지 못했습니다.'
}

function initialTransactionForm(
  currentUserId: number,
  household: CurrentHousehold,
  accounts: Account[],
  categories: Category[],
  occurredOn: string,
): TransactionFormState {
  const currentMemberId = household.members
    .find((member) => member.userId === currentUserId)
    ?.memberId.toString() ?? ''
  const sourceAccountId = accounts
    .find((account) => !account.archived
      && account.nature === 'ASSET'
      && account.type !== 'CREDIT_CARD')
    ?.id.toString() ?? ''
  return {
    type: 'EXPENSE',
    amount: '',
    scope: 'PERSONAL',
    ownerMemberId: currentMemberId,
    payerMemberId: currentMemberId,
    categoryId: categories.find((category) => category.type === 'EXPENSE')?.id.toString() ?? '',
    accountId: accounts.find((account) => isPrimaryAccountForType('EXPENSE', account))
      ?.id.toString() ?? '',
    sourceAccountId,
    destinationAccountId: accounts
      .find((account) => !account.archived && account.id.toString() !== sourceAccountId)
      ?.id.toString() ?? '',
    occurredOn,
    memo: '',
  }
}

function transactionToForm(
  transaction: LedgerTransaction,
  timeZone: string,
): TransactionFormState {
  return {
    type: transaction.type,
    amount: transaction.amount.toString(),
    scope: transaction.scope ?? 'PERSONAL',
    ownerMemberId: transaction.owner?.memberId.toString() ?? '',
    payerMemberId: transaction.payer?.memberId.toString() ?? '',
    categoryId: transaction.category?.id.toString() ?? '',
    accountId: entryByRole(transaction, 'PRIMARY')?.account.id.toString() ?? '',
    sourceAccountId: entryByRole(transaction, 'SOURCE')?.account.id.toString() ?? '',
    destinationAccountId: entryByRole(transaction, 'DESTINATION')?.account.id.toString() ?? '',
    occurredOn: dateInTimeZone(new Date(transaction.occurredAt), timeZone),
    memo: transaction.memo ?? '',
  }
}

export function QuickEntrySheet({
  currentUserId,
  household,
  accounts,
  categories,
  selectedDate,
  editing,
  onRequestClose,
  onSaved,
}: {
  currentUserId: number
  household: CurrentHousehold
  accounts: Account[]
  categories: Category[]
  selectedDate: string
  editing: LedgerTransaction | null
  onRequestClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState(() => editing
    ? transactionToForm(editing, household.timezone)
    : initialTransactionForm(currentUserId, household, accounts, categories, selectedDate))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const amountRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    amountRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) {
        event.preventDefault()
        onRequestClose()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onRequestClose, pending])

  const matchingCategories = categories.filter((category) => category.type === form.type)
  const primaryAccounts = accounts.filter((account) => isPrimaryAccountForType(form.type, account))
  const sourceAccounts = accounts.filter(
    (account) => !account.archived
      && account.nature === 'ASSET'
      && account.type !== 'CREDIT_CARD',
  )
  const destinationAccounts = accounts.filter(
    (account) => !account.archived && account.id.toString() !== form.sourceAccountId,
  )

  function change<K extends keyof TransactionFormState>(key: K, value: TransactionFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function selectType(type: LedgerTransaction['type']) {
    const nextSource = sourceAccounts[0]?.id.toString() ?? ''
    const currentMemberId = household.members
      .find((member) => member.userId === currentUserId)
      ?.memberId.toString() ?? ''
    setForm((current) => ({
      ...current,
      type,
      categoryId: type === 'TRANSFER'
        ? ''
        : categories.find((category) => category.type === type)?.id.toString() ?? '',
      accountId: type === 'TRANSFER'
        ? ''
        : accounts.find((account) => isPrimaryAccountForType(type, account))?.id.toString() ?? '',
      sourceAccountId: type === 'TRANSFER' ? nextSource : '',
      destinationAccountId: type === 'TRANSFER'
        ? accounts.find((account) => !account.archived && account.id.toString() !== nextSource)
          ?.id.toString() ?? ''
        : '',
      ownerMemberId: type === 'TRANSFER'
        ? current.ownerMemberId
        : current.ownerMemberId || currentMemberId,
      payerMemberId: type === 'EXPENSE'
        ? current.payerMemberId || currentMemberId
        : '',
    }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    setSuccess(null)
    try {
      if (!form.amount || Number(form.amount) <= 0) {
        throw new Error('금액을 확인해 주세요.')
      }
      if (form.type === 'TRANSFER') {
        if (!form.sourceAccountId || !form.destinationAccountId) {
          throw new Error('출금 Account와 입금 Account를 확인해 주세요.')
        }
        if (form.sourceAccountId === form.destinationAccountId) {
          throw new Error('출금 Account와 입금 Account는 달라야 합니다.')
        }
      } else if (!form.categoryId || !form.accountId) {
        throw new Error('Category와 Account를 확인해 주세요.')
      } else if (form.scope === 'PERSONAL' && !form.ownerMemberId) {
        throw new Error('개인 거래의 Owner를 확인해 주세요.')
      }

      const input = {
        type: form.type,
        amount: Number(form.amount),
        scope: form.type === 'TRANSFER' ? null : form.scope,
        ownerMemberId:
          form.type !== 'TRANSFER' && form.scope === 'PERSONAL'
            ? Number(form.ownerMemberId)
            : null,
        payerMemberId:
          form.type === 'EXPENSE' && form.payerMemberId ? Number(form.payerMemberId) : null,
        categoryId: form.type === 'TRANSFER' ? null : Number(form.categoryId),
        accountId: form.type === 'TRANSFER' ? null : Number(form.accountId),
        sourceAccountId: form.type === 'TRANSFER' ? Number(form.sourceAccountId) : null,
        destinationAccountId:
          form.type === 'TRANSFER' ? Number(form.destinationAccountId) : null,
        occurredAt: noonInTimeZone(form.occurredOn, household.timezone),
        memo: form.memo.trim() || null,
        adjustmentType: 'NORMAL' as const,
        reversesTransactionId: null,
      }
      if (editing) {
        await updateTransaction(editing.id, editing.version, input)
      } else {
        await createTransaction(input)
      }
      setSuccess(editing ? '수정했어요 🐾' : '저장했어요 🐾')
      onSaved()
      await new Promise((resolve) => window.setTimeout(resolve, 500))
      onRequestClose()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop">
      <section
        className="bottom-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-entry-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Quick Entry</p>
            <h2 id="quick-entry-title">{editing ? '거래 수정' : '빠른 입력'}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="빠른 입력 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <form className="entry-form" onSubmit={submit}>
          <div className="segmented-control" aria-label="거래 유형">
            {(['EXPENSE', 'INCOME', 'TRANSFER'] as const).map((type) => (
              <button
                key={type}
                type="button"
                className={form.type === type ? 'is-active' : ''}
                aria-pressed={form.type === type}
                onClick={() => selectType(type)}
              >
                {type === 'EXPENSE' ? '지출' : type === 'INCOME' ? '수입' : '이체'}
              </button>
            ))}
          </div>
          <label className="amount-field">
            금액
            <span>
              <input
                ref={amountRef}
                required
                autoFocus
                min="1"
                inputMode="numeric"
                type="number"
                value={form.amount}
                onChange={(event) => change('amount', event.target.value)}
              /> 원
            </span>
          </label>
          {form.type !== 'TRANSFER' && (
            <label>
              범위
              <select
                value={form.scope}
                onChange={(event) => change(
                  'scope',
                  event.target.value as TransactionFormState['scope'],
                )}
              >
                <option value="PERSONAL">개인</option>
                <option value="SHARED">공동</option>
              </select>
            </label>
          )}
          {form.type !== 'TRANSFER' && form.scope === 'PERSONAL' && (
            <label>
              Owner
              <select
                required
                value={form.ownerMemberId}
                onChange={(event) => change('ownerMemberId', event.target.value)}
              >
                {household.members.map((member) => (
                  <option key={member.memberId} value={member.memberId}>
                    {member.displayName}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.type === 'EXPENSE' && (
            <label>
              Payer (선택)
              <select
                value={form.payerMemberId}
                onChange={(event) => change('payerMemberId', event.target.value)}
              >
                <option value="">지정 안 함</option>
                {household.members.map((member) => (
                  <option key={member.memberId} value={member.memberId}>
                    {member.displayName}
                  </option>
                ))}
              </select>
            </label>
          )}
          {form.type !== 'TRANSFER' && (
            <label>
              Category
              <select
                required
                value={form.categoryId}
                onChange={(event) => change('categoryId', event.target.value)}
              >
                <option value="">선택</option>
                {matchingCategories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name}</option>
                ))}
              </select>
            </label>
          )}
          {form.type !== 'TRANSFER' && (
            <label>
              Account
              <select
                required
                value={form.accountId}
                onChange={(event) => change('accountId', event.target.value)}
              >
                <option value="">선택</option>
                {primaryAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </label>
          )}
          {form.type === 'TRANSFER' && (
            <label>
              출금 Account
              <select
                required
                value={form.sourceAccountId}
                onChange={(event) => {
                  const sourceAccountId = event.target.value
                  setForm((current) => ({
                    ...current,
                    sourceAccountId,
                    destinationAccountId: current.destinationAccountId === sourceAccountId
                      ? accounts.find((account) =>
                        !account.archived && account.id.toString() !== sourceAccountId,
                      )?.id.toString() ?? ''
                      : current.destinationAccountId,
                  }))
                }}
              >
                <option value="">선택</option>
                {sourceAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </label>
          )}
          {form.type === 'TRANSFER' && (
            <label>
              입금 Account
              <select
                required
                value={form.destinationAccountId}
                onChange={(event) => change('destinationAccountId', event.target.value)}
              >
                <option value="">선택</option>
                {destinationAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{account.name}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            날짜
            <input
              required
              type="date"
              value={form.occurredOn}
              onChange={(event) => change('occurredOn', event.target.value)}
            />
          </label>
          <label className="memo-field">
            메모 (선택)
            <input value={form.memo} onChange={(event) => change('memo', event.target.value)} />
          </label>
          <button className="primary-button sheet-submit" type="submit" disabled={pending}>
            {pending ? '저장 중…' : editing ? '수정 저장' : '거래 저장'}
          </button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {success && <p className="save-success" role="status">{success}</p>}
      </section>
    </div>
  )
}
