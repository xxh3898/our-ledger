import { type FormEvent, useEffect, useRef, useState } from 'react'
import { todayInTimeZone } from './dateTime.ts'
import {
  type Account,
  type Category,
  type CurrentHousehold,
  type RecurrenceFrequency,
  type RecurringTransaction,
  type RecurringTransactionInput,
  LedgerApiError,
  createRecurringTransaction,
  updateRecurringTransaction,
} from './ledgerApi.ts'
import { isPrimaryAccountForType } from './transactionUtils.ts'
import { UI_VOCABULARY } from './uiVocabulary.ts'

type FormState = {
  name: string
  type: RecurringTransaction['type']
  amount: string
  scope: 'PERSONAL' | 'SHARED'
  ownerMemberId: string
  payerMemberId: string
  categoryId: string
  accountId: string
  sourceAccountId: string
  destinationAccountId: string
  frequency: RecurrenceFrequency
  intervalValue: string
  startDate: string
  endDate: string
  scheduledLocalTime: string
  memo: string
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '반복 거래를 저장하지 못했습니다.'
}

function accountIdByRole(
  recurring: RecurringTransaction,
  role: 'PRIMARY' | 'SOURCE' | 'DESTINATION',
) {
  return recurring.accounts.find((item) => item.role === role)?.account.id.toString() ?? ''
}

function initialForm(
  currentUserId: number,
  household: CurrentHousehold,
  accounts: Account[],
  categories: Category[],
  editing: RecurringTransaction | null,
): FormState {
  if (editing) {
    return {
      name: editing.name,
      type: editing.type,
      amount: editing.amount.toString(),
      scope: editing.scope ?? 'PERSONAL',
      ownerMemberId: editing.owner?.memberId.toString() ?? '',
      payerMemberId: editing.payer?.memberId.toString() ?? '',
      categoryId: editing.category?.id.toString() ?? '',
      accountId: accountIdByRole(editing, 'PRIMARY'),
      sourceAccountId: accountIdByRole(editing, 'SOURCE'),
      destinationAccountId: accountIdByRole(editing, 'DESTINATION'),
      frequency: editing.frequency,
      intervalValue: editing.intervalValue.toString(),
      startDate: editing.startDate,
      endDate: editing.endDate ?? '',
      scheduledLocalTime: editing.scheduledLocalTime.slice(0, 5),
      memo: editing.memo ?? '',
    }
  }
  const memberId = household.members
    .find((member) => member.userId === currentUserId)?.memberId.toString() ?? ''
  const source = accounts.find((account) => !account.archived
    && account.nature === 'ASSET' && account.type !== 'CREDIT_CARD')
  const destination = accounts.find((account) => !account.archived
    && account.id !== source?.id)
  return {
    name: '',
    type: 'EXPENSE',
    amount: '',
    scope: 'PERSONAL',
    ownerMemberId: memberId,
    payerMemberId: memberId,
    categoryId: categories.find((category) => category.type === 'EXPENSE')?.id.toString() ?? '',
    accountId: accounts.find((account) => isPrimaryAccountForType('EXPENSE', account))
      ?.id.toString() ?? '',
    sourceAccountId: source?.id.toString() ?? '',
    destinationAccountId: destination?.id.toString() ?? '',
    frequency: 'MONTHLY',
    intervalValue: '1',
    startDate: todayInTimeZone(household.timezone),
    endDate: '',
    scheduledLocalTime: '09:00',
    memo: '',
  }
}

export function RecurringTransactionSheet({
  currentUserId,
  household,
  accounts,
  categories,
  editing,
  onRequestClose,
  onSaved,
}: {
  currentUserId: number
  household: CurrentHousehold
  accounts: Account[]
  categories: Category[]
  editing: RecurringTransaction | null
  onRequestClose: () => void
  onSaved: (saved: RecurringTransaction) => void
}) {
  const [form, setForm] = useState(() => initialForm(
    currentUserId, household, accounts, categories, editing,
  ))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
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
  const sourceAccounts = accounts.filter((account) => !account.archived
    && account.nature === 'ASSET' && account.type !== 'CREDIT_CARD')
  const destinationAccounts = accounts.filter((account) => !account.archived
    && account.id.toString() !== form.sourceAccountId)

  function change<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  function selectType(type: RecurringTransaction['type']) {
    setForm((current) => {
      if (type === current.type) return current
      const currentMemberId = household.members
        .find((member) => member.userId === currentUserId)?.memberId.toString() ?? ''
      const sourceAccount = sourceAccounts[0]
      const destinationAccount = accounts.find((account) => !account.archived
        && account.id !== sourceAccount?.id)
      return {
        ...current,
        type,
        categoryId: type === 'TRANSFER'
          ? ''
          : categories.find((category) => category.type === type)?.id.toString() ?? '',
        accountId: type === 'TRANSFER'
          ? ''
          : accounts.find((account) => isPrimaryAccountForType(type, account))?.id.toString() ?? '',
        sourceAccountId: type === 'TRANSFER' ? sourceAccount?.id.toString() ?? '' : '',
        destinationAccountId: type === 'TRANSFER'
          ? destinationAccount?.id.toString() ?? ''
          : '',
        ownerMemberId: type === 'TRANSFER' ? '' : current.ownerMemberId || currentMemberId,
        payerMemberId: type === 'EXPENSE' ? current.payerMemberId || currentMemberId : '',
      }
    })
  }

  function toInput(): RecurringTransactionInput {
    if (!form.name.trim() || !form.amount || Number(form.amount) <= 0) {
      throw new Error('이름과 금액을 확인해 주세요.')
    }
    if (!form.intervalValue || Number(form.intervalValue) <= 0) {
      throw new Error('반복 간격은 1 이상이어야 합니다.')
    }
    if (form.endDate && form.endDate < form.startDate) {
      throw new Error('종료일은 시작일보다 빠를 수 없습니다.')
    }
    if (form.type === 'TRANSFER') {
      if (!form.sourceAccountId || !form.destinationAccountId
        || form.sourceAccountId === form.destinationAccountId) {
        throw new Error('출금 Account와 입금 Account를 확인해 주세요.')
      }
    } else if (!form.categoryId || !form.accountId) {
      throw new Error('Category와 Account를 확인해 주세요.')
    } else if (form.scope === 'PERSONAL' && !form.ownerMemberId) {
      throw new Error(`개인 거래의 ${UI_VOCABULARY.transactionOwner}를 확인해 주세요.`)
    }
    return {
      name: form.name.trim(),
      type: form.type,
      amount: Number(form.amount),
      scope: form.type === 'TRANSFER' ? null : form.scope,
      ownerMemberId: form.type !== 'TRANSFER' && form.scope === 'PERSONAL'
        ? Number(form.ownerMemberId) : null,
      payerMemberId: form.type === 'EXPENSE' && form.payerMemberId
        ? Number(form.payerMemberId) : null,
      categoryId: form.type === 'TRANSFER' ? null : Number(form.categoryId),
      accountId: form.type === 'TRANSFER' ? null : Number(form.accountId),
      sourceAccountId: form.type === 'TRANSFER' ? Number(form.sourceAccountId) : null,
      destinationAccountId: form.type === 'TRANSFER'
        ? Number(form.destinationAccountId) : null,
      frequency: form.frequency,
      intervalValue: Number(form.intervalValue),
      startDate: form.startDate,
      endDate: form.endDate || null,
      scheduledLocalTime: form.scheduledLocalTime,
      memo: form.memo.trim() || null,
      autoPost: true,
      active: editing?.active ?? true,
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    try {
      const input = toInput()
      const saved = editing
        ? await updateRecurringTransaction(editing.id, editing.version, input)
        : await createRecurringTransaction(input)
      onSaved(saved)
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop recurring-sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pending) onRequestClose()
    }}>
      <section
        className="bottom-sheet recurring-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="recurring-sheet-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Recurring</p>
            <h2 id="recurring-sheet-title">{editing ? '반복 거래 수정' : '반복 거래 추가'}</h2>
          </div>
          <button type="button" className="icon-button" aria-label="반복 거래 닫기"
            disabled={pending} onClick={onRequestClose}>×</button>
        </header>
        <form className="entry-form recurring-form" onSubmit={submit}>
          <label>이름<input ref={nameRef} required value={form.name}
            onChange={(event) => change('name', event.target.value)} /></label>
          <div className="segmented-control" aria-label="반복 거래 유형">
            {(['EXPENSE', 'INCOME', 'TRANSFER'] as const).map((type) => (
              <button key={type} type="button" aria-pressed={form.type === type}
                className={form.type === type ? 'is-active' : ''} onClick={() => selectType(type)}>
                {type === 'EXPENSE' ? '지출' : type === 'INCOME' ? '수입' : '이체'}
              </button>
            ))}
          </div>
          <label>금액<input required min="1" type="number" inputMode="numeric"
            value={form.amount} onChange={(event) => change('amount', event.target.value)} /></label>
          {form.type !== 'TRANSFER' && (
            <>
              <label>범위<select value={form.scope}
                onChange={(event) => change('scope', event.target.value as FormState['scope'])}>
                <option value="PERSONAL">개인</option><option value="SHARED">공동</option>
              </select></label>
              {form.scope === 'PERSONAL' && (
                <label>
                  {UI_VOCABULARY.transactionOwner}
                  <select required value={form.ownerMemberId}
                    onChange={(event) => change('ownerMemberId', event.target.value)}>
                    {household.members.map((member) => <option key={member.memberId}
                      value={member.memberId}>{member.displayName}</option>)}
                  </select>
                </label>
              )}
              {form.type === 'EXPENSE' && (
                <label>
                  {UI_VOCABULARY.payer} (선택)
                  <select value={form.payerMemberId}
                    onChange={(event) => change('payerMemberId', event.target.value)}>
                    <option value="">지정 안 함</option>
                    {household.members.map((member) => <option key={member.memberId}
                      value={member.memberId}>{member.displayName}</option>)}
                  </select>
                </label>
              )}
              <label>Category<select required value={form.categoryId}
                onChange={(event) => change('categoryId', event.target.value)}>
                <option value="">선택</option>
                {matchingCategories.map((category) => <option key={category.id}
                  value={category.id}>{category.name}</option>)}
              </select></label>
              <label>Account<select required value={form.accountId}
                onChange={(event) => change('accountId', event.target.value)}>
                <option value="">선택</option>
                {primaryAccounts.map((account) => <option key={account.id}
                  value={account.id}>{account.name}</option>)}
              </select></label>
            </>
          )}
          {form.type === 'TRANSFER' && <>
            <label>출금 Account<select required value={form.sourceAccountId}
              onChange={(event) => change('sourceAccountId', event.target.value)}>
              <option value="">선택</option>{sourceAccounts.map((account) => <option
                key={account.id} value={account.id}>{account.name}</option>)}
            </select></label>
            <label>입금 Account<select required value={form.destinationAccountId}
              onChange={(event) => change('destinationAccountId', event.target.value)}>
              <option value="">선택</option>{destinationAccounts.map((account) => <option
                key={account.id} value={account.id}>{account.name}</option>)}
            </select></label>
          </>}
          <div className="form-grid">
            <label>주기<select value={form.frequency}
              onChange={(event) => change('frequency', event.target.value as RecurrenceFrequency)}>
              <option value="DAILY">일</option><option value="WEEKLY">주</option>
              <option value="MONTHLY">개월</option><option value="YEARLY">년</option>
            </select></label>
            <label>간격<input required min="1" type="number" value={form.intervalValue}
              onChange={(event) => change('intervalValue', event.target.value)} /></label>
            <label>시작일<input required type="date" value={form.startDate}
              min={editing?.startDate === form.startDate ? undefined : todayInTimeZone(household.timezone)}
              onChange={(event) => change('startDate', event.target.value)} /></label>
            <label>종료일 (선택)<input type="date" value={form.endDate}
              min={form.startDate} onChange={(event) => change('endDate', event.target.value)} /></label>
            <label>실행 시간<input required type="time" value={form.scheduledLocalTime}
              onChange={(event) => change('scheduledLocalTime', event.target.value)} /></label>
          </div>
          {(form.frequency === 'MONTHLY' || form.frequency === 'YEARLY') && <p className="field-hint">
            짧은 달과 윤년에는 마지막 유효일에 반영하고 다음 주기에는 원래 시작일 기준으로 돌아갑니다.
          </p>}
          <label>메모 (선택)<textarea maxLength={500} value={form.memo}
            onChange={(event) => change('memo', event.target.value)} /></label>
          {editing && <p className="field-hint">
            수정 내용은 앞으로 생성될 거래에만 적용되며 이미 생성된 거래는 바뀌지 않습니다.
          </p>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" type="submit" disabled={pending}>
            {pending ? '저장 중…' : editing ? '반복 거래 수정' : '반복 거래 저장'}
          </button>
        </form>
      </section>
    </div>
  )
}
