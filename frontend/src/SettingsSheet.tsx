import { type FormEvent, useState } from 'react'
import { todayInTimeZone } from './dateTime.ts'
import {
  type Account,
  type Category,
  type CategoryGroup,
  type CurrentHousehold,
  LedgerApiError,
  archiveAccount,
  archiveCategory,
  archiveCategoryGroup,
  createAccount,
  createCategory,
  createCategoryGroup,
} from './ledgerApi.ts'

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '요청을 처리하지 못했습니다.'
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
