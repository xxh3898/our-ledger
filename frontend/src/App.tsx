import { type FormEvent, useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  type Account,
  type Category,
  type CategoryGroup,
  type CurrentHousehold,
  type CurrentUser,
  type LedgerTransaction,
  LedgerApiError,
  archiveAccount,
  archiveCategory,
  archiveCategoryGroup,
  createAccount,
  createCategory,
  createCategoryGroup,
  createTransaction,
  deleteTransaction,
  loadCurrentUser,
  loadLedgerData,
  updateTransaction,
} from './ledgerApi.ts'

type ViewState =
  | { status: 'loading' }
  | { status: 'ready'; user: CurrentUser }
  | { status: 'authentication-required' }
  | { status: 'access-denied'; code?: string }
  | { status: 'error' }

type LedgerData = Awaited<ReturnType<typeof loadLedgerData>>

function zonedParts(value: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(value)
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((item) => item.type === type)?.value)
  return {
    year: part('year'),
    month: part('month'),
    day: part('day'),
    hour: part('hour'),
    minute: part('minute'),
    second: part('second'),
  }
}

function dateInTimeZone(value: Date, timeZone: string) {
  const { year, month, day } = zonedParts(value, timeZone)
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function noonInTimeZone(date: string, timeZone: string) {
  const [year, month, day] = date.split('-').map(Number)
  const localNoon = Date.UTC(year, month - 1, day, 12)
  let instant = localNoon

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const parts = zonedParts(new Date(instant), timeZone)
    const representedAsUtc = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    )
    instant = localNoon - (representedAsUtc - instant)
  }

  return new Date(instant).toISOString()
}

function today(timeZone: string) {
  return dateInTimeZone(new Date(), timeZone)
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '요청을 처리하지 못했습니다.'
}

function IdentityCard({ user }: { user: CurrentUser }) {
  return (
    <article className="identity-card" aria-label="현재 사용자와 Household">
      <div className="avatar" aria-hidden="true">
        {user.displayName.slice(0, 1)}
      </div>
      <div className="identity-copy">
        <p>현재 사용자</p>
        <h2>{user.displayName}</h2>
        <span>{user.email}</span>
      </div>
      <dl>
        <div>
          <dt>Household</dt>
          <dd>{user.householdName}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{user.role}</dd>
        </div>
      </dl>
    </article>
  )
}

function AccessState({ state }: { state: ViewState }) {
  if (state.status === 'loading') {
    return (
      <div className="identity-state" role="status">
        <span className="status-dot status-dot--loading" aria-hidden="true" />
        현재 사용자와 Household를 확인하고 있습니다.
      </div>
    )
  }

  if (state.status === 'authentication-required') {
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>인증이 필요합니다.</strong>
        <span>Cloudflare Access 인증 후 다시 열어 주세요.</span>
      </div>
    )
  }

  if (state.status === 'access-denied') {
    const isUnregistered = state.code === 'USER_NOT_REGISTERED'
    const isDisabled = state.code === 'USER_DISABLED'
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>
          {isUnregistered
            ? '등록된 사용자가 아닙니다.'
            : isDisabled
              ? '비활성화된 사용자입니다.'
              : 'Household 접근 권한이 없습니다.'}
        </strong>
        <span>내부 User와 Household membership을 확인해 주세요.</span>
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div className="identity-state identity-state--error" role="alert">
        <strong>현재 정보를 불러오지 못했습니다.</strong>
        <span>잠시 뒤 다시 시도해 주세요.</span>
      </div>
    )
  }

  return <IdentityCard user={state.user} />
}

function AccountSetup({
  household,
  accounts,
  onChanged,
}: {
  household: CurrentHousehold
  accounts: Account[]
  onChanged: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState<Account['type']>('CHECKING')
  const [nature, setNature] = useState<Account['nature']>('ASSET')
  const [ownership, setOwnership] = useState<Account['ownership']>('PERSONAL')
  const [ownerMemberId, setOwnerMemberId] = useState(
    household.members[0]?.memberId.toString() ?? '',
  )
  const [openingBalance, setOpeningBalance] = useState('0')
  const [openingBalanceAsOf, setOpeningBalanceAsOf] = useState(
    today(household.timezone),
  )
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await createAccount({
        name,
        institution: null,
        type,
        nature,
        ownership,
        ownerMemberId: ownership === 'PERSONAL' ? Number(ownerMemberId) : null,
        openingBalance: Number(openingBalance),
        openingBalanceAsOf,
        currency: 'KRW',
        lastFour: null,
        savingsEnabled: type === 'SAVINGS',
        sortOrder: accounts.length,
      })
      setName('')
      setOpeningBalance('0')
      await onChanged()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  async function archive(account: Account) {
    setPending(true)
    setError(null)
    try {
      await archiveAccount(account)
      await onChanged()
    } catch (archiveError) {
      setError(errorMessage(archiveError))
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="accounts-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Account</p>
          <h2 id="accounts-title">계좌 설정</h2>
        </div>
        <span className="count-badge">{accounts.length}</span>
      </div>
      <form className="compact-form" onSubmit={submit}>
        <label>
          계좌 이름
          <input required value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          유형
          <select
            value={type}
            onChange={(event) => {
              const nextType = event.target.value as Account['type']
              setType(nextType)
              setNature(nextType === 'CREDIT_CARD' ? 'LIABILITY' : 'ASSET')
            }}
          >
            <option value="CHECKING">입출금</option>
            <option value="SAVINGS">저축</option>
            <option value="CASH">현금</option>
            <option value="CREDIT_CARD">신용카드</option>
            <option value="OTHER">기타</option>
          </select>
        </label>
        <label>
          소유
          <select
            value={ownership}
            onChange={(event) => setOwnership(event.target.value as Account['ownership'])}
          >
            <option value="PERSONAL">개인</option>
            <option value="SHARED">공동</option>
          </select>
        </label>
        {ownership === 'PERSONAL' && (
          <label>
            소유자
            <select
              required
              value={ownerMemberId}
              onChange={(event) => setOwnerMemberId(event.target.value)}
            >
              {household.members.map((member) => (
                <option key={member.memberId} value={member.memberId}>
                  {member.displayName}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          기초 잔액
          <input
            inputMode="numeric"
            type="number"
            value={openingBalance}
            onChange={(event) => setOpeningBalance(event.target.value)}
          />
        </label>
        <label>
          잔액 기준일
          <input
            required
            type="date"
            value={openingBalanceAsOf}
            onChange={(event) => setOpeningBalanceAsOf(event.target.value)}
          />
        </label>
        <input type="hidden" value={nature} readOnly />
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? '저장 중…' : '계좌 추가'}
        </button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      <ul className="reference-list">
        {accounts.map((account) => (
          <li key={account.id}>
            <div>
              <strong>{account.name}</strong>
              <span>{account.ownership === 'SHARED' ? '공동' : account.owner?.displayName}</span>
            </div>
            <div className="reference-actions">
              <b>{account.currentBalance.toLocaleString('ko-KR')}원</b>
              <button type="button" disabled={pending} onClick={() => void archive(account)}>
                보관
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

function CategorySetup({
  groups,
  categories,
  onChanged,
}: {
  groups: CategoryGroup[]
  categories: Category[]
  onChanged: () => Promise<void>
}) {
  const [groupName, setGroupName] = useState('')
  const [groupType, setGroupType] = useState<CategoryGroup['type']>('EXPENSE')
  const [categoryName, setCategoryName] = useState('')
  const [categoryType, setCategoryType] = useState<Category['type']>('EXPENSE')
  const [groupId, setGroupId] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const matchingGroups = groups.filter((group) => group.type === categoryType)

  async function submitGroup(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await createCategoryGroup({ name: groupName, type: groupType, sortOrder: groups.length })
      setGroupName('')
      await onChanged()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  async function submitCategory(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await createCategory({
        groupId: groupId ? Number(groupId) : null,
        name: categoryName,
        type: categoryType,
        iconKey: null,
        colorKey: null,
        sortOrder: categories.filter((category) => category.type === categoryType).length,
      })
      setCategoryName('')
      await onChanged()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  async function archiveReference(reference: CategoryGroup | Category) {
    setPending(true)
    setError(null)
    try {
      if ('group' in reference) {
        await archiveCategory(reference)
      } else {
        await archiveCategoryGroup(reference)
      }
      await onChanged()
    } catch (archiveError) {
      setError(errorMessage(archiveError))
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="panel" aria-labelledby="categories-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Category</p>
          <h2 id="categories-title">분류 설정</h2>
        </div>
        <span className="count-badge">{categories.length}</span>
      </div>
      <form className="compact-form compact-form--row" onSubmit={submitGroup}>
        <label>
          Group 이름
          <input required value={groupName} onChange={(event) => setGroupName(event.target.value)} />
        </label>
        <label>
          Group 유형
          <select
            value={groupType}
            onChange={(event) => setGroupType(event.target.value as CategoryGroup['type'])}
          >
            <option value="EXPENSE">지출</option>
            <option value="INCOME">수입</option>
          </select>
        </label>
        <button type="submit" disabled={pending}>Group 추가</button>
      </form>
      <form className="compact-form" onSubmit={submitCategory}>
        <label>
          Category 이름
          <input
            required
            value={categoryName}
            onChange={(event) => setCategoryName(event.target.value)}
          />
        </label>
        <label>
          Category 유형
          <select
            value={categoryType}
            onChange={(event) => {
              setCategoryType(event.target.value as Category['type'])
              setGroupId('')
            }}
          >
            <option value="EXPENSE">지출</option>
            <option value="INCOME">수입</option>
          </select>
        </label>
        <label>
          Group
          <select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
            <option value="">그룹 없음</option>
            {matchingGroups.map((group) => (
              <option key={group.id} value={group.id}>{group.name}</option>
            ))}
          </select>
        </label>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? '저장 중…' : 'Category 추가'}
        </button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      <ul className="reference-list">
        {groups.map((group) => (
          <li key={`group-${group.id}`}>
            <div><strong>{group.name}</strong><span>{group.type} Group</span></div>
            <button type="button" disabled={pending} onClick={() => void archiveReference(group)}>
              보관
            </button>
          </li>
        ))}
        {categories.map((category) => (
          <li key={`category-${category.id}`}>
            <div>
              <strong>{category.name}</strong>
              <span>{category.group?.name ?? '그룹 없음'} · {category.type}</span>
            </div>
            <button type="button" disabled={pending} onClick={() => void archiveReference(category)}>
              보관
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

type TransactionFormState = {
  type: LedgerTransaction['type']
  amount: string
  scope: LedgerTransaction['scope']
  ownerMemberId: string
  payerMemberId: string
  categoryId: string
  accountId: string
  occurredOn: string
  memo: string
}

function initialTransactionForm(
  household: CurrentHousehold,
  accounts: Account[],
  categories: Category[],
): TransactionFormState {
  return {
    type: 'EXPENSE',
    amount: '',
    scope: 'PERSONAL',
    ownerMemberId: household.members[0]?.memberId.toString() ?? '',
    payerMemberId: household.members[0]?.memberId.toString() ?? '',
    categoryId: categories.find((category) => category.type === 'EXPENSE')?.id.toString() ?? '',
    accountId: accounts.find((account) => account.nature === 'ASSET')?.id.toString() ?? '',
    occurredOn: today(household.timezone),
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
    scope: transaction.scope,
    ownerMemberId: transaction.owner?.memberId.toString() ?? '',
    payerMemberId: transaction.payer?.memberId.toString() ?? '',
    categoryId: transaction.category.id.toString(),
    accountId: transaction.account.id.toString(),
    occurredOn: dateInTimeZone(new Date(transaction.occurredAt), timeZone),
    memo: transaction.memo ?? '',
  }
}

function QuickEntry({
  household,
  accounts,
  categories,
  editing,
  onCancelEdit,
  onChanged,
}: {
  household: CurrentHousehold
  accounts: Account[]
  categories: Category[]
  editing: LedgerTransaction | null
  onCancelEdit: () => void
  onChanged: () => Promise<void>
}) {
  const [form, setForm] = useState(() => initialTransactionForm(household, accounts, categories))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (editing) {
      setForm(transactionToForm(editing, household.timezone))
      setError(null)
    }
  }, [editing, household.timezone])

  const matchingCategories = categories.filter((category) => category.type === form.type)
  const assetAccounts = accounts.filter(
    (account) => account.nature === 'ASSET' && account.type !== 'CREDIT_CARD',
  )

  function change<K extends keyof TransactionFormState>(key: K, value: TransactionFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      if (!form.categoryId || !form.accountId || !form.amount) {
        throw new Error('금액, Category, Account를 확인해 주세요.')
      }
      const input = {
        type: form.type,
        amount: Number(form.amount),
        scope: form.scope,
        ownerMemberId: form.scope === 'PERSONAL' ? Number(form.ownerMemberId) : null,
        payerMemberId:
          form.type === 'EXPENSE' && form.payerMemberId ? Number(form.payerMemberId) : null,
        categoryId: Number(form.categoryId),
        accountId: Number(form.accountId),
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
      setForm(initialTransactionForm(household, accounts, categories))
      onCancelEdit()
      await onChanged()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="panel quick-entry" aria-labelledby="quick-entry-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Quick entry</p>
          <h2 id="quick-entry-title">{editing ? '거래 수정' : '빠른 입력'}</h2>
        </div>
        {editing && <span className="count-badge">#{editing.id}</span>}
      </div>
      <form className="entry-form" onSubmit={submit}>
        <div className="segmented-control" aria-label="거래 유형">
          {(['EXPENSE', 'INCOME'] as const).map((type) => (
            <button
              key={type}
              type="button"
              className={form.type === type ? 'is-active' : ''}
              onClick={() => {
                change('type', type)
                change('categoryId', categories.find((item) => item.type === type)?.id.toString() ?? '')
                if (type === 'INCOME') change('payerMemberId', '')
              }}
            >
              {type === 'EXPENSE' ? '지출' : '수입'}
            </button>
          ))}
        </div>
        <label className="amount-field">
          금액
          <span><input
            required
            min="1"
            inputMode="numeric"
            type="number"
            value={form.amount}
            onChange={(event) => change('amount', event.target.value)}
          /> 원</span>
        </label>
        <label>
          범위
          <select
            value={form.scope}
            onChange={(event) => change('scope', event.target.value as LedgerTransaction['scope'])}
          >
            <option value="PERSONAL">개인</option>
            <option value="SHARED">공동</option>
          </select>
        </label>
        {form.scope === 'PERSONAL' && (
          <label>
            Owner
            <select
              required
              value={form.ownerMemberId}
              onChange={(event) => change('ownerMemberId', event.target.value)}
            >
              {household.members.map((member) => (
                <option key={member.memberId} value={member.memberId}>{member.displayName}</option>
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
                <option key={member.memberId} value={member.memberId}>{member.displayName}</option>
              ))}
            </select>
          </label>
        )}
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
        <label>
          Account
          <select
            required
            value={form.accountId}
            onChange={(event) => change('accountId', event.target.value)}
          >
            <option value="">선택</option>
            {assetAccounts.map((account) => (
              <option key={account.id} value={account.id}>{account.name}</option>
            ))}
          </select>
        </label>
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
        <div className="form-actions">
          {editing && <button type="button" onClick={onCancelEdit}>취소</button>}
          <button className="primary-button" type="submit" disabled={pending}>
            {pending ? '저장 중…' : editing ? '수정 저장' : '거래 저장'}
          </button>
        </div>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  )
}

function TransactionList({
  transactions,
  timeZone,
  onEdit,
  onChanged,
}: {
  transactions: LedgerTransaction[]
  timeZone: string
  onEdit: (transaction: LedgerTransaction) => void
  onChanged: () => Promise<void>
}) {
  const [deleting, setDeleting] = useState<number | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function remove(transaction: LedgerTransaction) {
    setDeleting(transaction.id)
    setError(null)
    try {
      await deleteTransaction(transaction.id, transaction.version)
      await onChanged()
    } catch (deleteError) {
      setError(errorMessage(deleteError))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <section className="panel transaction-panel" aria-labelledby="transactions-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Recent</p>
          <h2 id="transactions-title">최근 거래</h2>
        </div>
        <span className="count-badge">{transactions.length}</span>
      </div>
      {transactions.length === 0 ? (
        <p className="empty-state">아직 거래가 없습니다. 첫 기록을 남겨 보세요.</p>
      ) : (
        <ul className="transaction-list">
          {transactions.map((transaction) => (
            <li key={transaction.id}>
              <div className={`transaction-sign transaction-sign--${transaction.type.toLowerCase()}`}>
                {transaction.type === 'INCOME' ? '+' : '−'}
              </div>
              <div className="transaction-copy">
                <strong>{transaction.category.name}</strong>
                <span>
                  {new Intl.DateTimeFormat('ko-KR', {
                    dateStyle: 'medium',
                    timeZone,
                  }).format(new Date(transaction.occurredAt))}
                  {' · '}{transaction.scope === 'SHARED' ? '공동' : transaction.owner?.displayName}
                  {' · '}{transaction.account.name}
                </span>
                {transaction.memo && <small>{transaction.memo}</small>}
              </div>
              <b className="transaction-amount">
                {transaction.type === 'INCOME' ? '+' : '−'}
                {transaction.amount.toLocaleString('ko-KR')}원
              </b>
              <div className="transaction-actions">
                <button
                  type="button"
                  aria-expanded={expanded === transaction.id}
                  onClick={() => setExpanded((current) => current === transaction.id ? null : transaction.id)}
                >
                  상세
                </button>
                <button type="button" onClick={() => onEdit(transaction)}>수정</button>
                <button
                  type="button"
                  disabled={deleting === transaction.id}
                  onClick={() => void remove(transaction)}
                >
                  {deleting === transaction.id ? '삭제 중…' : '삭제'}
                </button>
              </div>
              {expanded === transaction.id && (
                <dl className="transaction-details">
                  <div><dt>Payer</dt><dd>{transaction.payer?.displayName ?? '지정 안 함'}</dd></div>
                  <div><dt>Entry</dt><dd>{transaction.entry.role} {transaction.entry.balanceDelta.toLocaleString('ko-KR')}</dd></div>
                  <div><dt>Version</dt><dd>{transaction.version}</dd></div>
                </dl>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  )
}

function BalanceSummary({ accounts }: { accounts: Account[] }) {
  const total = useMemo(
    () => accounts
      .filter((account) => account.nature === 'ASSET')
      .reduce((sum, account) => sum + account.currentBalance, 0),
    [accounts],
  )
  return (
    <aside className="balance-summary" aria-label="ASSET Account 현재 잔액">
      <span>현재 ASSET 잔액</span>
      <strong>{total.toLocaleString('ko-KR')}원</strong>
      <small>opening balance + 미삭제 Entry</small>
    </aside>
  )
}

function LedgerDashboard() {
  const [state, setState] = useState<
    | { status: 'loading' }
    | { status: 'ready'; data: LedgerData }
    | { status: 'error'; message: string }
  >({ status: 'loading' })
  const [editing, setEditing] = useState<LedgerTransaction | null>(null)

  async function refresh() {
    try {
      const data = await loadLedgerData()
      setState({ status: 'ready', data })
      setEditing((current) =>
        current ? data.transactions.find((item) => item.id === current.id) ?? null : null,
      )
    } catch (error) {
      setState({ status: 'error', message: errorMessage(error) })
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void loadLedgerData(controller.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [])

  if (state.status === 'loading') {
    return <div className="ledger-state" role="status">가계부 데이터를 불러오고 있습니다.</div>
  }
  if (state.status === 'error') {
    return (
      <div className="ledger-state ledger-state--error" role="alert">
        <strong>가계부를 불러오지 못했습니다.</strong>
        <span>{state.message}</span>
        <button type="button" onClick={() => void refresh()}>다시 시도</button>
      </div>
    )
  }

  const { household, accounts, groups, categories, transactions } = state.data
  return (
    <div className="ledger-dashboard">
      <BalanceSummary accounts={accounts} />
      <div className="setup-grid">
        <AccountSetup household={household} accounts={accounts} onChanged={refresh} />
        <CategorySetup groups={groups} categories={categories} onChanged={refresh} />
      </div>
      <div className="ledger-grid">
        <QuickEntry
          household={household}
          accounts={accounts}
          categories={categories}
          editing={editing}
          onCancelEdit={() => setEditing(null)}
          onChanged={refresh}
        />
        <TransactionList
          transactions={transactions}
          timeZone={household.timezone}
          onEdit={setEditing}
          onChanged={refresh}
        />
      </div>
    </div>
  )
}

function App() {
  const [state, setState] = useState<ViewState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void loadCurrentUser(controller.signal)
      .then((user) => setState({ status: 'ready', user }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        if (error instanceof LedgerApiError && error.status === 401) {
          setState({ status: 'authentication-required' })
        } else if (error instanceof LedgerApiError && error.status === 403) {
          setState({ status: 'access-denied', code: error.code })
        } else {
          setState({ status: 'error' })
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">둘이 함께 쌓는 하나의 기록</p>
        <h1 id="page-title">우리의 장부</h1>
        <p className="hero-copy">
          검증된 Household 경계 안에서 Account와 Category, 수입과 지출을 함께 기록합니다.
        </p>
      </section>

      <section className="identity" aria-labelledby="identity-title">
        <div>
          <p className="section-kicker">Slice 2</p>
          <h2 id="identity-title">안전한 가계부</h2>
          <p className="section-copy">
            현재 사용자와 Household를 확인한 뒤 이 Household의 장부만 엽니다.
          </p>
        </div>
        <AccessState state={state} />
      </section>

      {state.status === 'ready' && <LedgerDashboard />}
    </main>
  )
}

export default App
