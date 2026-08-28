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
  type: 'INCOME' | 'EXPENSE' | 'TRANSFER'
  amount: number
  scope: 'PERSONAL' | 'SHARED' | null
  owner: { memberId: number; userId: number; displayName: string } | null
  payer: { memberId: number; userId: number; displayName: string } | null
  category: { id: number; name: string; type: 'INCOME' | 'EXPENSE'; archived: boolean } | null
  occurredAt: string
  memo: string | null
  adjustmentType: 'NORMAL' | 'REFUND'
  version: number
  entries: Array<{
    id: number
    role: 'PRIMARY' | 'SOURCE' | 'DESTINATION'
    balanceDelta: number
    account: {
      id: number
      name: string
      type: Account['type']
      nature: Account['nature']
      archived: boolean
    }
  }>
}

export type CalendarMonth = {
  month: string
  timezone: string
  summary: {
    netSpendingAmount: number
    previousMonthNetSpendingAmount: number
    differenceAmount: number
  }
  days: Array<{
    date: string
    transactionCount: number
    netSpendingAmount: number
  }>
}

export type CalendarFilter =
  | { scope: 'ALL'; ownerMemberId: null }
  | { scope: 'PERSONAL'; ownerMemberId: number }
  | { scope: 'SHARED'; ownerMemberId: null }

export type BudgetScope = 'HOUSEHOLD' | 'PERSONAL' | 'SHARED'

export type BudgetOwner = {
  memberId: number
  userId: number
  displayName: string
}

export type BudgetCategory = {
  id: number
  name: string
  type: 'EXPENSE'
  archived: boolean
}

export type BudgetResponse = {
  id: number
  month: string
  scope: BudgetScope
  owner: BudgetOwner | null
  category: BudgetCategory | null
  amount: number
  version: number
  createdAt: string
  updatedAt: string
}

export type BudgetMonth = {
  month: string
  timezone: string
  scopes: Array<{
    scope: BudgetScope
    owner: BudgetOwner | null
    budgetId: number | null
    version: number | null
    budgetAmount: number | null
    spentAmount: number
    remainingAmount: number | null
    exceeded: boolean
  }>
  categories: Array<{
    budgetId: number
    version: number
    scope: BudgetScope
    owner: BudgetOwner | null
    category: BudgetCategory
    budgetAmount: number
    spentAmount: number
    remainingAmount: number
    exceeded: boolean
  }>
}

export type BudgetInput = {
  month: string
  scope: BudgetScope
  ownerMemberId: number | null
  categoryId: number | null
  amount: number
}

export type StatisticsData = {
  period: {
    from: string
    to: string
    timezone: string
  }
  summary: {
    incomeAmount: number
    netSpendingAmount: number
    savingsAmount: number | null
    savingsRate: number | null
  }
  comparison: {
    from: string
    to: string
    incomeAmount: number
    netSpendingAmount: number
    savingsAmount: number | null
    savingsRate: number | null
    incomeDifferenceAmount: number
    netSpendingDifferenceAmount: number
    savingsDifferenceAmount: number | null
    incomePercentChange: number | null
    netSpendingPercentChange: number | null
    savingsPercentChange: number | null
    savingsRateDifferencePoints: number | null
  } | null
  subjects: Array<{
    scope: 'PERSONAL' | 'SHARED'
    owner: BudgetOwner | null
    netSpendingAmount: number
  }>
  categories: Array<{
    category: { id: number; name: string; archived: boolean }
    netSpendingAmount: number
    shareRate: number | null
  }>
  accounts: Array<{
    account: {
      id: number
      name: string
      type: Account['type']
      nature: Account['nature']
      archived: boolean
    }
    netSpendingAmount: number
  }>
  months: Array<{
    month: string
    incomeAmount: number
    netSpendingAmount: number
    savingsAmount: number | null
    savingsRate: number | null
  }>
}

export type SavingsActivity = {
  transactionId: number
  occurredAt: string
  amount: number
  savingsImpactAmount: number
  sourceAccount: { id: number; name: string }
  destinationAccount: { id: number; name: string }
  memo: string | null
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
  categoryId: number | null
  accountId: number | null
  sourceAccountId: number | null
  destinationAccountId: number | null
  occurredAt: string
  memo: string | null
  adjustmentType: 'NORMAL'
  reversesTransactionId: null
}

export type RefundSummary = {
  originalTransactionId: number
  originalAmount: number
  refundedAmount: number
  remainingRefundableAmount: number
  refunds: Array<{
    id: number
    amount: number
    occurredAt: string
    memo: string | null
    version: number
  }>
}

export type RefundInput = {
  amount: number
  occurredAt: string
  memo: string | null
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

export async function loadReferenceData(signal?: AbortSignal) {
  const [household, accounts, groups, categories] = await Promise.all([
    request<CurrentHousehold>('/api/v1/households/current', { signal }),
    request<Account[]>('/api/v1/accounts', { signal }),
    request<CategoryGroup[]>('/api/v1/category-groups', { signal }),
    request<Category[]>('/api/v1/categories', { signal }),
  ])
  return { household, accounts, groups, categories }
}

function applyCalendarFilter(parameters: URLSearchParams, filter: CalendarFilter) {
  if (filter.scope === 'PERSONAL') {
    parameters.set('scope', 'PERSONAL')
    parameters.set('ownerMemberId', filter.ownerMemberId.toString())
  } else if (filter.scope === 'SHARED') {
    parameters.set('scope', 'SHARED')
  }
}

export function loadCalendarMonth(
  month: string,
  filter: CalendarFilter,
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams({ month })
  applyCalendarFilter(parameters, filter)
  return request<CalendarMonth>(`/api/v1/calendar/month?${parameters}`, { signal })
}

export function loadDayTransactions(
  date: string,
  filter: CalendarFilter,
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams({ from: date, to: date })
  applyCalendarFilter(parameters, filter)
  return request<LedgerTransaction[]>(`/api/v1/transactions?${parameters}`, { signal })
}

export function loadBudgetMonth(month: string, signal?: AbortSignal) {
  const parameters = new URLSearchParams({ month })
  return request<BudgetMonth>(`/api/v1/budgets?${parameters}`, { signal })
}

export function loadStatistics(
  range: {
    from: string
    to: string
    compareFrom: string
    compareTo: string
  },
  filter: CalendarFilter,
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams(range)
  applyCalendarFilter(parameters, filter)
  return request<StatisticsData>(`/api/v1/statistics?${parameters}`, { signal })
}

export function loadStatisticsTransactions(
  range: { from: string; to: string },
  filter: CalendarFilter,
  target: {
    type: 'INCOME' | 'EXPENSE'
    categoryId?: number
    accountId?: number
  },
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams({
    from: range.from,
    to: range.to,
    type: target.type,
  })
  applyCalendarFilter(parameters, filter)
  if (target.categoryId !== undefined) {
    parameters.set('categoryId', target.categoryId.toString())
  }
  if (target.accountId !== undefined) {
    parameters.set('accountId', target.accountId.toString())
  }
  return request<LedgerTransaction[]>(`/api/v1/transactions?${parameters}`, { signal })
}

export function loadSavingsActivities(
  range: { from: string; to: string },
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams(range)
  return request<SavingsActivity[]>(
    `/api/v1/statistics/savings-activities?${parameters}`,
    { signal },
  )
}

function lastDayOfMonth(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  return `${month}-${String(new Date(Date.UTC(year, monthNumber, 0)).getUTCDate()).padStart(2, '0')}`
}

export function loadBudgetTransactions(
  month: string,
  scope: BudgetScope,
  ownerMemberId: number | null,
  categoryId: number | null,
  signal?: AbortSignal,
) {
  const parameters = new URLSearchParams({
    from: `${month}-01`,
    to: lastDayOfMonth(month),
    type: 'EXPENSE',
  })
  if (scope === 'PERSONAL' && ownerMemberId !== null) {
    parameters.set('scope', 'PERSONAL')
    parameters.set('ownerMemberId', ownerMemberId.toString())
  } else if (scope === 'SHARED') {
    parameters.set('scope', 'SHARED')
  }
  if (categoryId !== null) parameters.set('categoryId', categoryId.toString())
  return request<LedgerTransaction[]>(`/api/v1/transactions?${parameters}`, { signal })
}

export function createBudget(input: BudgetInput) {
  return request<BudgetResponse>('/api/v1/budgets', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateBudget(budgetId: number, version: number, input: BudgetInput) {
  return request<BudgetResponse>(`/api/v1/budgets/${budgetId}`, {
    method: 'PATCH',
    body: JSON.stringify({ version, ...input }),
  })
}

export function deleteBudget(budgetId: number, version: number) {
  return request<void>(`/api/v1/budgets/${budgetId}?version=${version}`, {
    method: 'DELETE',
  })
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

export function loadRefundSummary(originalTransactionId: number, signal?: AbortSignal) {
  return request<RefundSummary>(
    `/api/v1/transactions/${originalTransactionId}/refunds`,
    { signal },
  )
}

export function createRefund(originalTransactionId: number, input: RefundInput) {
  return request<LedgerTransaction>(
    `/api/v1/transactions/${originalTransactionId}/refunds`,
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}
