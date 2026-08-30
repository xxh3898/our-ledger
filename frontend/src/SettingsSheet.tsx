import { type FormEvent, useEffect, useRef, useState } from 'react'
import { todayInTimeZone } from './dateTime.ts'
import { RecurringTransactionSheet } from './RecurringTransactionSheet.tsx'
import {
  type Account,
  type Category,
  type CategoryGroup,
  type CurrentHousehold,
  type RecurringTransaction,
  type RecurringTransactionInput,
  LedgerApiError,
  archiveAccount,
  archiveCategory,
  archiveCategoryGroup,
  createAccount,
  createCategory,
  createCategoryGroup,
  downloadTransactionCsv,
  loadRecurringTransactions,
  updateRecurringTransaction,
} from './ledgerApi.ts'

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '요청을 처리하지 못했습니다.'
}

function recurringInput(recurring: RecurringTransaction): RecurringTransactionInput {
  const account = (role: 'PRIMARY' | 'SOURCE' | 'DESTINATION') =>
    recurring.accounts.find((item) => item.role === role)?.account.id ?? null
  return {
    name: recurring.name,
    type: recurring.type,
    amount: recurring.amount,
    scope: recurring.scope,
    ownerMemberId: recurring.owner?.memberId ?? null,
    payerMemberId: recurring.payer?.memberId ?? null,
    categoryId: recurring.category?.id ?? null,
    accountId: account('PRIMARY'),
    sourceAccountId: account('SOURCE'),
    destinationAccountId: account('DESTINATION'),
    frequency: recurring.frequency,
    intervalValue: recurring.intervalValue,
    startDate: recurring.startDate,
    endDate: recurring.endDate,
    scheduledLocalTime: recurring.scheduledLocalTime.slice(0, 5),
    memo: recurring.memo,
    autoPost: true,
    active: recurring.active,
  }
}

function TransactionExport({ household }: { household: CurrentHousehold }) {
  const today = todayInTimeZone(household.timezone)
  const [from, setFrom] = useState(() => `${today.slice(0, 7)}-01`)
  const [to, setTo] = useState(() => today)
  const [pending, setPending] = useState(false)
  const pendingRef = useRef(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pendingRef.current) return
    pendingRef.current = true
    setPending(true)
    setError(null)
    setSuccess(false)
    let objectUrl: string | null = null
    try {
      const download = await downloadTransactionCsv(from, to)
      objectUrl = URL.createObjectURL(download.blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = download.filename
      link.hidden = true
      document.body.append(link)
      try {
        link.click()
      } finally {
        link.remove()
      }
      setSuccess(true)
    } catch (downloadError) {
      setError(errorMessage(downloadError))
    } finally {
      if (objectUrl !== null) URL.revokeObjectURL(objectUrl)
      pendingRef.current = false
      setPending(false)
    }
  }

  return (
    <section className="settings-panel" aria-labelledby="transaction-export-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Export</p>
          <h3 id="transaction-export-title">데이터 내보내기</h3>
        </div>
      </div>
      <p className="field-hint">
        현재 Household의 유효 거래를 CSV로 내보냅니다. 삭제된 거래는 제외하며,
        CSV는 운영 backup의 대체물이 아닙니다.
      </p>
      <form className="compact-form" onSubmit={submit}>
        <label>
          시작일
          <input
            required
            type="date"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label>
          종료일
          <input
            required
            type="date"
            value={to}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        <button className="primary-button" type="submit" disabled={pending}>
          {pending ? 'CSV 준비 중…' : 'CSV 내려받기'}
        </button>
      </form>
      {pending && <p role="status">CSV를 준비하고 있어요.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {success && <p className="save-success" role="status">CSV를 내려받았어요.</p>}
    </section>
  )
}

function scheduleText(recurring: RecurringTransaction) {
  const unit = recurring.frequency === 'DAILY' ? '일'
    : recurring.frequency === 'WEEKLY' ? '주'
      : recurring.frequency === 'MONTHLY' ? '개월' : '년'
  const every = recurring.frequency === 'DAILY' ? '매일'
    : recurring.frequency === 'WEEKLY' ? '매주'
      : recurring.frequency === 'MONTHLY' ? '매월' : '매년'
  const interval = recurring.intervalValue === 1 ? every : `${recurring.intervalValue}${unit}마다`
  const start = new Date(`${recurring.startDate}T00:00:00Z`)
  const anchor = recurring.frequency === 'WEEKLY'
    ? `${['일', '월', '화', '수', '목', '금', '토'][start.getUTCDay()]}요일`
    : recurring.frequency === 'MONTHLY'
      ? `${Number(recurring.startDate.slice(8))}일`
      : recurring.frequency === 'YEARLY'
        ? `${Number(recurring.startDate.slice(5, 7))}월 ${Number(recurring.startDate.slice(8))}일`
        : ''
  return `${interval}${anchor ? ` ${anchor}` : ''} · ${recurring.scheduledLocalTime.slice(0, 5)}`
}

function RecurringSetup({
  currentUserId,
  household,
  accounts,
  categories,
}: {
  currentUserId: number
  household: CurrentHousehold
  accounts: Account[]
  categories: Category[]
}) {
  const [items, setItems] = useState<RecurringTransaction[]>([])
  const [loading, setLoading] = useState(true)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<RecurringTransaction | null>(null)
  const editorOpenerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void loadRecurringTransactions(controller.signal)
      .then((data) => setItems(data))
      .catch((loadError: unknown) => {
        if (!(loadError instanceof DOMException && loadError.name === 'AbortError')) {
          setError(errorMessage(loadError))
        }
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  function openEditor(recurring: RecurringTransaction | null, opener: HTMLElement) {
    editorOpenerRef.current = opener
    setEditing(recurring)
    setEditorOpen(true)
  }

  function closeEditor() {
    setEditorOpen(false)
    setEditing(null)
    window.setTimeout(() => editorOpenerRef.current?.focus(), 0)
  }

  function saved(savedItem: RecurringTransaction) {
    setItems((current) => {
      const exists = current.some((item) => item.id === savedItem.id)
      return exists
        ? current.map((item) => item.id === savedItem.id ? savedItem : item)
        : [...current, savedItem]
    })
    closeEditor()
  }

  async function toggleActive(recurring: RecurringTransaction) {
    if (pendingId !== null) return
    setPendingId(recurring.id)
    setError(null)
    try {
      const updated = await updateRecurringTransaction(
        recurring.id,
        recurring.version,
        { ...recurringInput(recurring), active: !recurring.active },
      )
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item))
    } catch (updateError) {
      setError(errorMessage(updateError))
    } finally {
      setPendingId(null)
    }
  }

  return (
    <section className="settings-panel recurring-settings" aria-labelledby="recurring-title">
      <div className="panel-heading">
        <div><p className="section-kicker">Recurring</p><h3 id="recurring-title">반복 거래</h3></div>
        <span className="count-badge">{items.length}</span>
      </div>
      <p className="field-hint">
        중지해도 이미 생성된 거래는 유지되며, 다시 시작해도 중지 기간은 소급 생성하지 않습니다.
      </p>
      <button className="primary-button" type="button"
        onClick={(event) => openEditor(null, event.currentTarget)}>+ 반복 거래 추가</button>
      {loading && <p role="status">반복 거래를 불러오고 있어요.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {!loading && items.length === 0 && <p className="list-state">등록된 반복 거래가 없어요.</p>}
      <ul className="reference-list recurring-list">
        {items.map((recurring) => (
          <li key={recurring.id}>
            <div>
              <strong>{recurring.name}</strong>
              <span>{recurring.amount.toLocaleString('ko-KR')}원 · {
                recurring.type === 'INCOME' ? '수입' : recurring.type === 'EXPENSE' ? '지출' : '이체'
              } · {recurring.scope === 'SHARED' ? '공동' : recurring.owner?.displayName ?? '계좌 간'}</span>
              <span>{scheduleText(recurring)} · {recurring.accounts.map((item) => item.account.name).join(' → ')}</span>
              {recurring.nextRecurrenceDate && <small>다음 {recurring.nextRecurrenceDate}</small>}
            </div>
            <div className="reference-actions recurring-actions">
              <b className={`status-badge status-badge--${recurring.status.toLowerCase()}`}>
                {recurring.status === 'ACTIVE' ? '활성' : recurring.status === 'PAUSED' ? '중지됨' : '종료됨'}
              </b>
              <button type="button" onClick={(event) => openEditor(recurring, event.currentTarget)}>
                수정
              </button>
              {recurring.status !== 'ENDED' && <button type="button"
                disabled={pendingId === recurring.id} onClick={() => void toggleActive(recurring)}>
                {pendingId === recurring.id ? '반영 중…' : recurring.active ? '중지' : '재개'}
              </button>}
            </div>
          </li>
        ))}
      </ul>
      {editorOpen && <RecurringTransactionSheet
        currentUserId={currentUserId}
        household={household}
        accounts={accounts}
        categories={categories}
        editing={editing}
        onRequestClose={closeEditor}
        onSaved={saved}
      />}
    </section>
  )
}

function AccountSetup({
  currentUserId,
  household,
  accounts,
  onChanged,
}: {
  currentUserId: number
  household: CurrentHousehold
  accounts: Account[]
  onChanged: () => Promise<void>
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState<Account['type']>('CHECKING')
  const [nature, setNature] = useState<Account['nature']>('ASSET')
  const [ownership, setOwnership] = useState<Account['ownership']>('PERSONAL')
  const [ownerMemberId, setOwnerMemberId] = useState(
    household.members.find((member) => member.userId === currentUserId)?.memberId.toString() ?? '',
  )
  const [openingBalance, setOpeningBalance] = useState('0')
  const [openingBalanceAsOf, setOpeningBalanceAsOf] = useState(
    todayInTimeZone(household.timezone),
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
    <section className="settings-panel" aria-labelledby="accounts-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Account</p>
          <h3 id="accounts-title">계좌 설정</h3>
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
        {type === 'CREDIT_CARD' && (
          <p className="field-hint">
            신용카드는 LIABILITY로 기록하며 저축 Account로 사용할 수 없습니다.
          </p>
        )}
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
    <section className="settings-panel" aria-labelledby="categories-title">
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Category</p>
          <h3 id="categories-title">분류 설정</h3>
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
            <button
              type="button"
              disabled={pending}
              onClick={() => void archiveReference(category)}
            >
              보관
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function SettingsSheet({
  currentUserId,
  household,
  accounts,
  groups,
  categories,
  onChanged,
  onRequestClose,
}: {
  currentUserId: number
  household: CurrentHousehold
  accounts: Account[]
  groups: CategoryGroup[]
  categories: Category[]
  onChanged: () => Promise<void>
  onRequestClose: () => void
}) {
  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onRequestClose()
    }}>
      <section
        className="settings-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <header className="sheet-header settings-header">
          <div>
            <p className="section-kicker">Settings</p>
            <h2 id="settings-title">장부 설정</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="설정 닫기"
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <div className="settings-content">
          <RecurringSetup
            currentUserId={currentUserId}
            household={household}
            accounts={accounts}
            categories={categories}
          />
          <TransactionExport household={household} />
          <AccountSetup
            currentUserId={currentUserId}
            household={household}
            accounts={accounts}
            onChanged={onChanged}
          />
          <CategorySetup groups={groups} categories={categories} onChanged={onChanged} />
        </div>
      </section>
    </div>
  )
}
