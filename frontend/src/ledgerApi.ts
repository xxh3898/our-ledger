export type CurrentUser = {
  userId: number
  email: string
  displayName: string
  householdId: number
  householdName: string
  role: 'OWNER' | 'MEMBER'
}

export type HouseholdMember = {
  memberId: number
  userId: number
  displayName: string
  role: 'OWNER' | 'MEMBER'
}

export type CurrentHousehold = {
  householdId: number
  name: string
  baseCurrency: string
  timezone: string
  members: HouseholdMember[]
}

export type Account = {
  id: number
  name: string
  institution: string | null
  type: 'CHECKING' | 'SAVINGS' | 'CASH' | 'CREDIT_CARD' | 'OTHER'
  nature: 'ASSET' | 'LIABILITY'
  ownership: 'PERSONAL' | 'SHARED'
  owner: { memberId: number; userId: number; displayName: string } | null
  openingBalance: number
  openingBalanceAsOf: string
  currentBalance: number
  currency: string
  lastFour: string | null
  savingsEnabled: boolean
  sortOrder: number
  archived: boolean
}

export type CategoryGroup = {
  id: number
  name: string
  type: 'INCOME' | 'EXPENSE'
  sortOrder: number
  archived: boolean
}

export type Category = {
  id: number
  group: { id: number; name: string; type: 'INCOME' | 'EXPENSE'; archived: boolean } | null
  name: string
  type: 'INCOME' | 'EXPENSE'
  iconKey: string | null
  colorKey: string | null
  sortOrder: number
  archived: boolean
}

export type LedgerTransaction = {
  id: number
  type: 'INCOME' | 'EXPENSE'
  amount: number
  scope: 'PERSONAL' | 'SHARED'
  owner: { memberId: number; userId: number; displayName: string } | null
  payer: { memberId: number; userId: number; displayName: string } | null
  category: { id: number; name: string; type: 'INCOME' | 'EXPENSE'; archived: boolean }
  account: {
    id: number
    name: string
    type: Account['type']
    nature: Account['nature']
    archived: boolean
  }
  occurredAt: string
  memo: string | null
  adjustmentType: 'NORMAL'
  version: number
  entry: { id: number; role: 'PRIMARY'; balanceDelta: number }
}

export type AccountInput = {
  name: string
  institution: string | null
  type: Account['type']
  nature: Account['nature']
  ownership: Account['ownership']
  ownerMemberId: number | null
  openingBalance: number
  openingBalanceAsOf: string
  currency: 'KRW'
  lastFour: string | null
  savingsEnabled: boolean
  sortOrder: number
}

export type CategoryGroupInput = {
  name: string
  type: CategoryGroup['type']
  sortOrder: number
}

export type CategoryInput = {
  groupId: number | null
  name: string
  type: Category['type']
  iconKey: string | null
  colorKey: string | null
  sortOrder: number
}

export type TransactionInput = {
  type: LedgerTransaction['type']
  amount: number
  scope: LedgerTransaction['scope']
  ownerMemberId: number | null
  payerMemberId: number | null
  categoryId: number
  accountId: number
  occurredAt: string
  memo: string | null
  adjustmentType: 'NORMAL'
  reversesTransactionId: null
}

export class LedgerApiError extends Error {
  readonly code?: string
  readonly status: number

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'LedgerApiError'
    this.status = status
    this.code = code
  }
}

function csrfToken(): string | null {
  const item = document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith('XSRF-TOKEN='))
  return item ? decodeURIComponent(item.slice('XSRF-TOKEN='.length)) : null
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) {
    headers.set('Content-Type', 'application/json')
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = csrfToken()
    if (token) {
      headers.set('X-XSRF-TOKEN', token)
    }
  }

  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers,
  })
  if (!response.ok) {
    const error = (await response.json().catch(() => ({}))) as {
      code?: string
      message?: string
    }
    throw new LedgerApiError(
      error.message ?? '요청을 처리하지 못했습니다.',
      response.status,
      error.code,
    )
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export async function loadCurrentUser(signal: AbortSignal): Promise<CurrentUser> {
  return request<CurrentUser>('/api/v1/me', { signal })
}

export async function loadLedgerData(signal?: AbortSignal) {
  const [household, accounts, groups, categories, transactions] = await Promise.all([
    request<CurrentHousehold>('/api/v1/households/current', { signal }),
    request<Account[]>('/api/v1/accounts', { signal }),
    request<CategoryGroup[]>('/api/v1/category-groups', { signal }),
    request<Category[]>('/api/v1/categories', { signal }),
    request<LedgerTransaction[]>('/api/v1/transactions', { signal }),
  ])
  return { household, accounts, groups, categories, transactions }
}

export function createAccount(input: AccountInput) {
  return request<Account>('/api/v1/accounts', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function archiveAccount(account: Account) {
  const input: AccountInput & { archived: boolean } = {
    name: account.name,
    institution: account.institution,
    type: account.type,
    nature: account.nature,
    ownership: account.ownership,
    ownerMemberId: account.owner?.memberId ?? null,
    openingBalance: account.openingBalance,
    openingBalanceAsOf: account.openingBalanceAsOf,
    currency: 'KRW',
    lastFour: account.lastFour,
    savingsEnabled: account.savingsEnabled,
    sortOrder: account.sortOrder,
    archived: true,
  }
  return request<Account>(`/api/v1/accounts/${account.id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export function createCategoryGroup(input: CategoryGroupInput) {
  return request<CategoryGroup>('/api/v1/category-groups', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function archiveCategoryGroup(group: CategoryGroup) {
  return request<CategoryGroup>(`/api/v1/category-groups/${group.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name: group.name, sortOrder: group.sortOrder, archived: true }),
  })
}

export function createCategory(input: CategoryInput) {
  return request<Category>('/api/v1/categories', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function archiveCategory(category: Category) {
  return request<Category>(`/api/v1/categories/${category.id}`, {
    method: 'PATCH',
    body: JSON.stringify({
      groupId: category.group?.id ?? null,
      name: category.name,
      iconKey: category.iconKey,
      colorKey: category.colorKey,
      sortOrder: category.sortOrder,
      archived: true,
    }),
  })
}

export function createTransaction(input: TransactionInput) {
  return request<LedgerTransaction>('/api/v1/transactions', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateTransaction(
  transactionId: number,
  version: number,
  input: TransactionInput,
) {
  return request<LedgerTransaction>(`/api/v1/transactions/${transactionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ version, ...input }),
  })
}

export function deleteTransaction(transactionId: number, version: number) {
  return request<void>(`/api/v1/transactions/${transactionId}?version=${version}`, {
    method: 'DELETE',
  })
}
