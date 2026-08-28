import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-08-28T03:00:00Z'))
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  window.history.replaceState({}, '', '/')
})

function jsonResponse(body: unknown, status = 200) {
  if (status === 204) return new Response(null, { status })
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const currentUser = {
  userId: 1,
  email: 'owner@example.test',
  displayName: 'Owner',
  householdId: 10,
  householdName: '테스트 Household',
  role: 'OWNER',
} as const

const currentHousehold = {
  householdId: 10,
  name: '테스트 Household',
  baseCurrency: 'KRW',
  timezone: 'Asia/Seoul',
  members: [
    { memberId: 100, userId: 1, displayName: 'Owner', role: 'OWNER' },
    { memberId: 101, userId: 2, displayName: 'Member', role: 'MEMBER' },
  ],
} as const

const checkingAccount = {
  id: 200,
  name: '주거래 통장',
  institution: null,
  type: 'CHECKING',
  nature: 'ASSET',
  ownership: 'PERSONAL',
  owner: { memberId: 100, userId: 1, displayName: 'Owner' },
  openingBalance: 1000,
  openingBalanceAsOf: '2026-08-01',
  currentBalance: 1000,
  currency: 'KRW',
  lastFour: null,
  savingsEnabled: false,
  sortOrder: 0,
  archived: false,
}

const savingsAccount = {
  ...checkingAccount,
  id: 201,
  name: '비상금 통장',
  type: 'SAVINGS',
  openingBalance: 0,
  currentBalance: 0,
  sortOrder: 1,
  savingsEnabled: true,
}

const expenseCategory = {
  id: 300,
  group: null,
  name: '식비',
  type: 'EXPENSE',
  iconKey: null,
  colorKey: null,
  sortOrder: 0,
  archived: false,
}

const incomeCategory = {
  ...expenseCategory,
  id: 301,
  name: '급여',
  type: 'INCOME',
}

const statisticsData = {
  period: { from: '2026-08-01', to: '2026-08-31', timezone: 'Asia/Seoul' },
  summary: {
    incomeAmount: 3_000_000,
    netSpendingAmount: 128_450,
    savingsAmount: 1_000_000,
    savingsRate: 33.3,
  },
  comparison: {
    from: '2026-07-01',
    to: '2026-07-31',
    incomeAmount: 2_800_000,
    netSpendingAmount: 150_000,
    savingsAmount: 900_000,
    savingsRate: 32.1,
    incomeDifferenceAmount: 200_000,
    netSpendingDifferenceAmount: -21_550,
    savingsDifferenceAmount: 100_000,
    incomePercentChange: 7.1,
    netSpendingPercentChange: -14.4,
    savingsPercentChange: 11.1,
    savingsRateDifferencePoints: 1.2,
  },
  subjects: [
    {
      scope: 'PERSONAL',
      owner: { memberId: 100, userId: 1, displayName: 'Owner' },
      netSpendingAmount: 80_000,
    },
    {
      scope: 'PERSONAL',
      owner: { memberId: 101, userId: 2, displayName: 'Member' },
      netSpendingAmount: 30_000,
    },
    { scope: 'SHARED', owner: null, netSpendingAmount: 18_450 },
  ],
  categories: [
    {
      category: { id: 300, name: '식비', archived: false },
      netSpendingAmount: 100_000,
      shareRate: 77.9,
    },
    {
      category: { id: 302, name: '지난 취미', archived: true },
      netSpendingAmount: 28_450,
      shareRate: 22.1,
    },
  ],
  accounts: [
    {
      account: {
        id: 200,
        name: '주거래 통장',
        type: 'CHECKING',
        nature: 'ASSET',
        archived: false,
      },
      netSpendingAmount: 128_450,
    },
  ],
  months: [
    {
      month: '2026-08',
      incomeAmount: 3_000_000,
      netSpendingAmount: 128_450,
      savingsAmount: 1_000_000,
      savingsRate: 33.3,
    },
  ],
}

const savingsActivities = [{
  transactionId: 900,
  occurredAt: '2026-08-10T12:00:00+09:00',
  amount: 1_000_000,
  savingsImpactAmount: 1_000_000,
  sourceAccount: { id: 200, name: '주거래 통장' },
  destinationAccount: { id: 201, name: '비상금 통장' },
  memo: '결혼자금',
  generatedFromRecurringId: null,
  recurrenceDate: null,
}]

function marriageGoal(overrides: Record<string, unknown> = {}) {
  return {
    id: 700,
    type: 'MARRIAGE',
    name: '우리 집까지',
    targetAmount: 100_000_000,
    version: 0,
    currentAmount: 32_400_000,
    achievementRate: 32.4,
    remainingAmount: 67_600_000,
    thisMonthSavingsAmount: 1_800_000,
    recentAverageMonthlySavingsAmount: 1_500_000,
    projectionStatus: 'PROJECTED',
    expectedAchievementMonth: '2030-06',
    monthlyTrend: [
      { month: '2026-03', savingsAmount: 0 },
      { month: '2026-04', savingsAmount: 900_000 },
      { month: '2026-05', savingsAmount: 1_100_000 },
      { month: '2026-06', savingsAmount: 1_400_000 },
      { month: '2026-07', savingsAmount: 2_000_000 },
      { month: '2026-08', savingsAmount: 1_800_000 },
    ],
    linkedAccounts: [{
      id: 201,
      name: '비상금 통장',
      ownership: 'PERSONAL',
      owner: { memberId: 100, displayName: 'Owner' },
      currentBalance: 32_400_000,
      startingBalance: 30_000_000,
      linkedAt: '2026-03-01T00:00:00Z',
      archived: false,
    }],
    recentSavingsActivities: [{
      ...savingsActivities[0],
      generatedFromRecurringId: 800,
      recurrenceDate: '2026-08-10',
    }],
    createdAt: '2026-03-01T00:00:00Z',
    updatedAt: '2026-08-01T00:00:00Z',
    ...overrides,
  }
}

function primaryTransaction({
  id,
  amount,
  ownerMemberId = 100,
  scope = 'PERSONAL',
  occurredAt = '2026-08-27T03:00:00Z',
  type = 'EXPENSE',
  memo = '점심',
}: {
  id: number
  amount: number
  ownerMemberId?: number
  scope?: 'PERSONAL' | 'SHARED'
  occurredAt?: string
  type?: 'EXPENSE' | 'INCOME'
  memo?: string | null
}) {
  const member = currentHousehold.members.find((item) => item.memberId === ownerMemberId)
  const category = type === 'EXPENSE' ? expenseCategory : incomeCategory
  return {
    id,
    type,
    amount,
    scope,
    owner: scope === 'PERSONAL' && member
      ? { memberId: member.memberId, userId: member.userId, displayName: member.displayName }
      : null,
    payer: null,
    category: { id: category.id, name: category.name, type: category.type, archived: false },
    occurredAt,
    memo,
    adjustmentType: 'NORMAL',
    generatedFromRecurringId: null,
    recurrenceDate: null,
    version: 0,
    entries: [{
      id: id + 1000,
      role: 'PRIMARY',
      balanceDelta: type === 'INCOME' ? amount : -amount,
      account: {
        id: 200,
        name: '주거래 통장',
        type: 'CHECKING',
        nature: 'ASSET',
        archived: false,
      },
    }],
  }
}

function transferTransaction(id: number, occurredAt = '2026-08-27T04:00:00Z') {
  return {
    id,
    type: 'TRANSFER',
    amount: 3000,
    scope: null,
    owner: null,
    payer: null,
    category: null,
    occurredAt,
    memo: '저축 이동',
    adjustmentType: 'NORMAL',
    generatedFromRecurringId: null,
    recurrenceDate: null,
    version: 0,
    entries: [
      {
        id: id + 1000,
        role: 'SOURCE',
        balanceDelta: -3000,
        account: {
          id: 200,
          name: '주거래 통장',
          type: 'CHECKING',
          nature: 'ASSET',
          archived: false,
        },
      },
      {
        id: id + 1001,
        role: 'DESTINATION',
        balanceDelta: 3000,
        account: {
          id: 201,
          name: '비상금 통장',
          type: 'SAVINGS',
          nature: 'ASSET',
          archived: false,
        },
      },
    ],
  }
}

function recurringRule(overrides: Record<string, unknown> = {}) {
  return {
    id: 800,
    name: '월급',
    type: 'INCOME',
    amount: 3_000_000,
    scope: 'PERSONAL',
    owner: { memberId: 100, displayName: 'Owner' },
    payer: null,
    category: { id: 301, name: '급여', archived: false },
    accounts: [{
      role: 'PRIMARY',
      account: {
        id: 200,
        name: '주거래 통장',
        type: 'CHECKING',
        nature: 'ASSET',
        archived: false,
      },
    }],
    frequency: 'MONTHLY',
    intervalValue: 1,
    startDate: '2026-08-28',
    endDate: null,
    scheduledLocalTime: '09:00:00',
    memo: null,
    autoPost: true,
    active: true,
    nextRecurrenceDate: '2026-09-28',
    status: 'ACTIVE',
    version: 0,
    ...overrides,
  }
}

function refundTransaction({
  id,
  original,
  amount,
  occurredAt = '2026-08-27T05:00:00Z',
  memo = '부분 환불',
}: {
  id: number
  original: ReturnType<typeof primaryTransaction>
  amount: number
  occurredAt?: string
  memo?: string | null
}) {
  const originalEntry = original.entries[0]
  return {
    ...original,
    id,
    amount,
    occurredAt,
    memo,
    adjustmentType: 'REFUND',
    reversesTransactionId: original.id,
    version: 0,
    entries: [{
      ...originalEntry,
      id: id + 1000,
      balanceDelta: -originalEntry.balanceDelta / Math.abs(originalEntry.balanceDelta) * amount,
    }],
  }
}

type RouterOptions = {
  accounts?: Array<Record<string, unknown>>
  groups?: Array<Record<string, unknown>>
  categories?: Array<Record<string, unknown>>
  transactions?: Array<Record<string, unknown>>
  budgets?: Array<Record<string, unknown>>
  recurringTransactions?: Array<Record<string, unknown>>
  failTransactionCreate?: boolean
  failRefundCreate?: boolean
  failBudgetCreate?: boolean
  failBudgetUpdate?: boolean
  budgetCreateGate?: Promise<void>
  refundCreateGate?: Promise<void>
  statistics?: Record<string, unknown>
  savingsActivities?: Array<Record<string, unknown>>
  statisticsGate?: Promise<void>
  failRecurringCreate?: boolean
  recurringCreateGate?: Promise<void>
  goal?: Record<string, unknown> | null
  goalReadGate?: Promise<void>
  goalMutationGate?: Promise<void>
  failGoalCreate?: boolean
  failGoalUpdate?: boolean
  failGoalLink?: boolean
  failGoalUnlink?: boolean
}

function transactionDate(occurredAt: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(occurredAt))
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

function installLedgerRouter(options: RouterOptions = {}) {
  const state = {
    accounts: [...(options.accounts ?? [checkingAccount, savingsAccount])],
    groups: [...(options.groups ?? [])],
    categories: [...(options.categories ?? [expenseCategory, incomeCategory])],
    transactions: [...(options.transactions ?? [])],
    budgets: [...(options.budgets ?? [])],
    recurringTransactions: [...(options.recurringTransactions ?? [])],
    goal: options.goal ?? null,
  }

  function goalViewResponse() {
    const linkedIds = new Set(
      ((state.goal?.linkedAccounts ?? []) as Array<Record<string, unknown>>)
        .map((account) => Number(account.id)),
    )
    const eligibleAccounts = state.accounts
      .filter((account) => account.nature === 'ASSET')
      .filter((account) => account.savingsEnabled === true)
      .filter((account) => account.archived !== true)
      .filter((account) => !linkedIds.has(Number(account.id)))
      .map((account) => ({
        id: account.id,
        name: account.name,
        ownership: account.ownership,
        owner: account.owner,
        currentBalance: account.currentBalance,
      }))
    return { goal: state.goal, eligibleAccounts }
  }

  function matchesFilter(transaction: Record<string, unknown>, url: URL) {
    const type = url.searchParams.get('type')
    if (type && transaction.type !== type) return false
    const categoryId = url.searchParams.get('categoryId')
    if (categoryId && Number((transaction.category as { id?: number } | null)?.id)
      !== Number(categoryId)) return false
    const scope = url.searchParams.get('scope')
    if (scope === 'SHARED') return transaction.scope === 'SHARED'
    if (scope === 'PERSONAL') {
      const owner = transaction.owner as { memberId?: number } | null
      return transaction.scope === 'PERSONAL'
        && owner?.memberId === Number(url.searchParams.get('ownerMemberId'))
    }
    return true
  }

  function calendarResponse(url: URL) {
    const month = url.searchParams.get('month') ?? '2026-08'
    const [year, monthNumber] = month.split('-').map(Number)
    const previousDate = new Date(Date.UTC(year, monthNumber - 2, 1))
    const previousMonth = `${previousDate.getUTCFullYear()}-${String(previousDate.getUTCMonth() + 1).padStart(2, '0')}`
    const filtered = state.transactions.filter((transaction) => matchesFilter(transaction, url))
    const net = (transaction: Record<string, unknown>) => {
      if (transaction.type !== 'EXPENSE') return 0
      return transaction.adjustmentType === 'REFUND'
        ? -Number(transaction.amount)
        : Number(transaction.amount)
    }
    const current = filtered.filter((transaction) =>
      transactionDate(String(transaction.occurredAt)).startsWith(month))
    const previous = filtered.filter((transaction) =>
      transactionDate(String(transaction.occurredAt)).startsWith(previousMonth))
    const days = new Map<string, { transactionCount: number; netSpendingAmount: number }>()
    current.forEach((transaction) => {
      const date = transactionDate(String(transaction.occurredAt))
      const day = days.get(date) ?? { transactionCount: 0, netSpendingAmount: 0 }
      day.transactionCount += 1
      day.netSpendingAmount += net(transaction)
      days.set(date, day)
    })
    const netSpendingAmount = current.reduce((sum, transaction) => sum + net(transaction), 0)
    const previousMonthNetSpendingAmount = previous
      .reduce((sum, transaction) => sum + net(transaction), 0)
    return {
      month,
      timezone: 'Asia/Seoul',
      summary: {
        netSpendingAmount,
        previousMonthNetSpendingAmount,
        differenceAmount: netSpendingAmount - previousMonthNetSpendingAmount,
      },
      days: [...days.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([date, day]) => ({ date, ...day })),
    }
  }

  function budgetOwner(memberId: unknown) {
    return memberReference(memberId)
  }

  function budgetCategory(categoryId: unknown) {
    const category = state.categories.find((item) => Number(item.id) === Number(categoryId))
    return category
      ? {
          id: category.id,
          name: category.name,
          type: category.type,
          archived: category.archived ?? false,
        }
      : null
  }

  function budgetSpent(
    month: string,
    scope: string,
    ownerMemberId: unknown,
    categoryId: unknown,
  ) {
    return state.transactions
      .filter((transaction) => transaction.type === 'EXPENSE')
      .filter((transaction) => transactionDate(String(transaction.occurredAt)).startsWith(month))
      .filter((transaction) => {
        if (scope === 'HOUSEHOLD') return true
        if (scope === 'SHARED') return transaction.scope === 'SHARED'
        const owner = transaction.owner as { memberId?: number } | null
        return transaction.scope === 'PERSONAL'
          && owner?.memberId === Number(ownerMemberId)
      })
      .filter((transaction) => categoryId == null
        || Number((transaction.category as { id?: number } | null)?.id) === Number(categoryId))
      .reduce((sum, transaction) => sum + (
        transaction.adjustmentType === 'REFUND'
          ? -Number(transaction.amount)
          : Number(transaction.amount)
      ), 0)
  }

  function budgetMonthResponse(url: URL) {
    const month = url.searchParams.get('month') ?? '2026-08'
    const row = (scope: string, ownerMemberId: number | null, categoryId: number | null) =>
      state.budgets.find((budget) => budget.month === month
        && budget.scope === scope
        && (budget.ownerMemberId ?? null) === ownerMemberId
        && (budget.categoryId ?? null) === categoryId)
    const scopeItem = (scope: string, ownerMemberId: number | null) => {
      const budget = row(scope, ownerMemberId, null)
      const spentAmount = budgetSpent(month, scope, ownerMemberId, null)
      const amount = budget ? Number(budget.amount) : null
      return {
        scope,
        owner: ownerMemberId === null ? null : budgetOwner(ownerMemberId),
        budgetId: budget?.id ?? null,
        version: budget?.version ?? null,
        budgetAmount: amount,
        spentAmount,
        remainingAmount: amount === null ? null : amount - spentAmount,
        exceeded: amount !== null && spentAmount > amount,
      }
    }
    const scopes = [
      scopeItem('HOUSEHOLD', null),
      ...currentHousehold.members.map((member) => scopeItem('PERSONAL', member.memberId)),
      scopeItem('SHARED', null),
    ]
    const categories = state.budgets
      .filter((budget) => budget.month === month && budget.categoryId != null)
      .map((budget) => {
        const spentAmount = budgetSpent(
          month,
          String(budget.scope),
          budget.ownerMemberId,
          budget.categoryId,
        )
        const amount = Number(budget.amount)
        return {
          budgetId: budget.id,
          version: budget.version,
          scope: budget.scope,
          owner: budget.ownerMemberId == null ? null : budgetOwner(budget.ownerMemberId),
          category: budgetCategory(budget.categoryId),
          budgetAmount: amount,
          spentAmount,
          remainingAmount: amount - spentAmount,
          exceeded: spentAmount > amount,
        }
      })
    return { month, timezone: 'Asia/Seoul', scopes, categories }
  }

  function budgetResource(budget: Record<string, unknown>) {
    return {
      id: budget.id,
      month: budget.month,
      scope: budget.scope,
      owner: budget.ownerMemberId == null ? null : budgetOwner(budget.ownerMemberId),
      category: budget.categoryId == null ? null : budgetCategory(budget.categoryId),
      amount: budget.amount,
      version: budget.version,
      createdAt: '2026-08-01T00:00:00Z',
      updatedAt: '2026-08-01T00:00:00Z',
    }
  }

  function memberReference(memberId: unknown) {
    const member = currentHousehold.members.find((item) => item.memberId === Number(memberId))
    return member
      ? { memberId: member.memberId, userId: member.userId, displayName: member.displayName }
      : null
  }

  function transactionResponse(inputBody: Record<string, unknown>, id: number, version: number) {
    const amount = Number(inputBody.amount)
    const type = String(inputBody.type)
    const category = state.categories.find((item) => Number(item.id) === Number(inputBody.categoryId))
    const account = state.accounts.find((item) => Number(item.id) === Number(inputBody.accountId))
    const source = state.accounts.find((item) => Number(item.id) === Number(inputBody.sourceAccountId))
    const destination = state.accounts.find(
      (item) => Number(item.id) === Number(inputBody.destinationAccountId),
    )
    const accountReference = (item: Record<string, unknown> | undefined) => ({
      id: item?.id,
      name: item?.name,
      type: item?.type,
      nature: item?.nature,
      archived: false,
    })
    return {
      id,
      type,
      amount,
      scope: inputBody.scope,
      owner: memberReference(inputBody.ownerMemberId),
      payer: memberReference(inputBody.payerMemberId),
      category: category
        ? { id: category.id, name: category.name, type: category.type, archived: false }
        : null,
      occurredAt: inputBody.occurredAt,
      memo: inputBody.memo,
      adjustmentType: 'NORMAL',
      generatedFromRecurringId: null,
      recurrenceDate: null,
      version,
      entries: type === 'TRANSFER'
        ? [
            { id: 501, role: 'SOURCE', balanceDelta: -amount, account: accountReference(source) },
            {
              id: 502,
              role: 'DESTINATION',
              balanceDelta: amount,
              account: accountReference(destination),
            },
          ]
        : [{
            id: 501,
            role: 'PRIMARY',
            balanceDelta: type === 'INCOME' ? amount : -amount,
            account: accountReference(account),
          }],
    }
  }

  function recurringResponse(inputBody: Record<string, unknown>, id: number, version: number) {
    const type = String(inputBody.type)
    const accountReference = (accountId: unknown) => {
      const account = state.accounts.find((item) => Number(item.id) === Number(accountId))
      return {
        id: account?.id,
        name: account?.name,
        type: account?.type,
        nature: account?.nature,
        archived: false,
      }
    }
    const accounts = type === 'TRANSFER'
      ? [
          { role: 'SOURCE', account: accountReference(inputBody.sourceAccountId) },
          { role: 'DESTINATION', account: accountReference(inputBody.destinationAccountId) },
        ]
      : [{ role: 'PRIMARY', account: accountReference(inputBody.accountId) }]
    const category = state.categories.find(
      (item) => Number(item.id) === Number(inputBody.categoryId),
    )
    const active = Boolean(inputBody.active)
    return {
      id,
      name: inputBody.name,
      type,
      amount: inputBody.amount,
      scope: inputBody.scope,
      owner: memberReference(inputBody.ownerMemberId),
      payer: memberReference(inputBody.payerMemberId),
      category: category ? { id: category.id, name: category.name, archived: false } : null,
      accounts,
      frequency: inputBody.frequency,
      intervalValue: inputBody.intervalValue,
      startDate: inputBody.startDate,
      endDate: inputBody.endDate,
      scheduledLocalTime: inputBody.scheduledLocalTime,
      memo: inputBody.memo,
      autoPost: true,
      active,
      nextRecurrenceDate: inputBody.startDate,
      status: active ? 'ACTIVE' : 'PAUSED',
      version,
    }
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = typeof input === 'string' ? input : input.toString()
    const url = new URL(path, 'http://ledger.test')
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.pathname === '/api/v1/me') return jsonResponse(currentUser)
    if (url.pathname === '/api/v1/households/current') return jsonResponse(currentHousehold)

    if (url.pathname === '/api/v1/goals/marriage' && method === 'GET') {
      if (options.goalReadGate) await options.goalReadGate
      return jsonResponse(goalViewResponse())
    }
    if (url.pathname === '/api/v1/goals/marriage' && method === 'POST') {
      if (options.goalMutationGate) await options.goalMutationGate
      if (options.failGoalCreate) {
        return jsonResponse({ code: 'GOAL_ALREADY_EXISTS', message: '중복 Goal' }, 409)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      state.goal = marriageGoal({
        name: inputBody.name,
        targetAmount: inputBody.targetAmount,
        currentAmount: 0,
        achievementRate: 0,
        remainingAmount: inputBody.targetAmount,
        thisMonthSavingsAmount: 0,
        recentAverageMonthlySavingsAmount: null,
        projectionStatus: 'INSUFFICIENT_HISTORY',
        expectedAchievementMonth: null,
        linkedAccounts: [],
        recentSavingsActivities: [],
      })
      return jsonResponse(goalViewResponse(), 201)
    }
    if (url.pathname === '/api/v1/goals/marriage' && method === 'PATCH') {
      if (options.goalMutationGate) await options.goalMutationGate
      if (options.failGoalUpdate) {
        return jsonResponse({ code: 'GOAL_VERSION_CONFLICT', message: 'stale Goal' }, 409)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      state.goal = {
        ...(state.goal ?? {}),
        name: inputBody.name,
        targetAmount: inputBody.targetAmount,
        version: Number(state.goal?.version ?? 0) + 1,
      }
      return jsonResponse(goalViewResponse())
    }
    const goalAccountMatch = url.pathname.match(/^\/api\/v1\/goals\/marriage\/accounts\/(\d+)$/)
    if (goalAccountMatch && method === 'POST') {
      if (options.goalMutationGate) await options.goalMutationGate
      if (options.failGoalLink) {
        return jsonResponse({
          code: 'GOAL_ACCOUNT_ALREADY_ASSIGNED',
          message: '이미 연결됨',
        }, 409)
      }
      const accountId = Number(goalAccountMatch[1])
      const account = state.accounts.find((item) => Number(item.id) === accountId)
      const linkedAccounts = [
        ...((state.goal?.linkedAccounts ?? []) as Array<Record<string, unknown>>),
        {
          id: account?.id,
          name: account?.name,
          ownership: account?.ownership,
          owner: account?.owner,
          currentBalance: account?.currentBalance,
          startingBalance: account?.currentBalance,
          linkedAt: '2026-08-28T03:00:00Z',
          archived: false,
        },
      ]
      state.goal = { ...(state.goal ?? {}), linkedAccounts }
      return jsonResponse(goalViewResponse(), 201)
    }
    if (goalAccountMatch && method === 'DELETE') {
      if (options.goalMutationGate) await options.goalMutationGate
      if (options.failGoalUnlink) {
        return jsonResponse({ code: 'RESOURCE_STATE_CONFLICT', message: '해제 실패' }, 409)
      }
      const accountId = Number(goalAccountMatch[1])
      state.goal = {
        ...(state.goal ?? {}),
        linkedAccounts: ((state.goal?.linkedAccounts ?? []) as Array<Record<string, unknown>>)
          .filter((account) => Number(account.id) !== accountId),
      }
      return jsonResponse(null, 204)
    }

    if (url.pathname === '/api/v1/accounts' && method === 'GET') return jsonResponse(state.accounts)
    if (url.pathname === '/api/v1/accounts' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = {
        ...checkingAccount,
        ...inputBody,
        id: 210 + state.accounts.length,
        currentBalance: inputBody.openingBalance,
        owner: memberReference(inputBody.ownerMemberId),
        archived: false,
      }
      state.accounts.push(created)
      return jsonResponse(created, 201)
    }
    if (url.pathname.startsWith('/api/v1/accounts/') && method === 'PATCH') {
      return jsonResponse({ ...state.accounts[0], archived: true })
    }

    if (url.pathname === '/api/v1/category-groups' && method === 'GET') {
      return jsonResponse(state.groups)
    }
    if (url.pathname === '/api/v1/category-groups' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = { id: 250, ...inputBody, archived: false }
      state.groups.push(created)
      return jsonResponse(created, 201)
    }
    if (url.pathname.startsWith('/api/v1/category-groups/') && method === 'PATCH') {
      return jsonResponse({ ...state.groups[0], archived: true })
    }

    if (url.pathname === '/api/v1/categories' && method === 'GET') {
      return jsonResponse(state.categories)
    }
    if (url.pathname === '/api/v1/categories' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = { id: 302, group: null, ...inputBody, archived: false }
      state.categories.push(created)
      return jsonResponse(created, 201)
    }
    if (url.pathname.startsWith('/api/v1/categories/') && method === 'PATCH') {
      return jsonResponse({ ...state.categories[0], archived: true })
    }

    if (url.pathname === '/api/v1/recurring-transactions' && method === 'GET') {
      return jsonResponse(state.recurringTransactions)
    }
    if (url.pathname === '/api/v1/recurring-transactions' && method === 'POST') {
      if (options.recurringCreateGate) await options.recurringCreateGate
      if (options.failRecurringCreate) {
        return jsonResponse({
          code: 'INVALID_REQUEST',
          message: '반복 일정을 확인해 주세요.',
        }, 400)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = recurringResponse(inputBody, 800 + state.recurringTransactions.length, 0)
      state.recurringTransactions.push(created)
      return jsonResponse(created, 201)
    }
    if (/^\/api\/v1\/recurring-transactions\/\d+$/.test(url.pathname) && method === 'PATCH') {
      const recurringId = Number(url.pathname.split('/').at(-1))
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const index = state.recurringTransactions.findIndex((item) => Number(item.id) === recurringId)
      const updated = recurringResponse(
        inputBody,
        recurringId,
        Number(state.recurringTransactions[index]?.version ?? 0) + 1,
      )
      state.recurringTransactions[index] = updated
      return jsonResponse(updated)
    }

    if (url.pathname === '/api/v1/calendar/month' && method === 'GET') {
      return jsonResponse(calendarResponse(url))
    }
    if (url.pathname === '/api/v1/statistics/savings-activities' && method === 'GET') {
      return jsonResponse(options.savingsActivities ?? savingsActivities)
    }
    if (url.pathname === '/api/v1/statistics' && method === 'GET') {
      if (options.statisticsGate) await options.statisticsGate
      return jsonResponse(options.statistics ?? statisticsData)
    }
    if (url.pathname === '/api/v1/budgets' && method === 'GET') {
      return jsonResponse(budgetMonthResponse(url))
    }
    if (url.pathname === '/api/v1/budgets' && method === 'POST') {
      if (options.budgetCreateGate) await options.budgetCreateGate
      if (options.failBudgetCreate) {
        return jsonResponse({
          code: 'BUDGET_DUPLICATE',
          message: '같은 Budget이 이미 있습니다.',
        }, 409)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = {
        id: 600 + state.budgets.length,
        version: 0,
        ...inputBody,
      }
      state.budgets.push(created)
      return jsonResponse(budgetResource(created), 201)
    }
    if (/^\/api\/v1\/budgets\/\d+$/.test(url.pathname) && method === 'PATCH') {
      if (options.failBudgetUpdate) {
        return jsonResponse({
          code: 'BUDGET_VERSION_CONFLICT',
          message: 'stale Budget',
        }, 409)
      }
      const budgetId = Number(url.pathname.split('/').at(-1))
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const index = state.budgets.findIndex((item) => Number(item.id) === budgetId)
      const current = state.budgets[index]
      const updated = {
        ...current,
        ...inputBody,
        id: budgetId,
        version: Number(current?.version ?? 0) + 1,
      }
      state.budgets[index] = updated
      return jsonResponse(budgetResource(updated))
    }
    if (/^\/api\/v1\/budgets\/\d+$/.test(url.pathname) && method === 'DELETE') {
      const budgetId = Number(url.pathname.split('/').at(-1))
      state.budgets = state.budgets.filter((item) => Number(item.id) !== budgetId)
      return jsonResponse(null, 204)
    }
    if (url.pathname === '/api/v1/transactions' && method === 'GET') {
      const from = url.searchParams.get('from')
      const to = url.searchParams.get('to')
      return jsonResponse(state.transactions.filter((transaction) => {
        const date = transactionDate(String(transaction.occurredAt))
        return matchesFilter(transaction, url)
          && (!from || date >= from)
          && (!to || date <= to)
      }))
    }
    if (url.pathname === '/api/v1/transactions' && method === 'POST') {
      if (options.failTransactionCreate) {
        return jsonResponse({
          code: 'CATEGORY_TYPE_MISMATCH',
          message: '분류를 확인해 주세요.',
        }, 422)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = transactionResponse(inputBody, 401 + state.transactions.length, 0)
      state.transactions.unshift(created)
      return jsonResponse(created, 201)
    }
    const refundMatch = url.pathname.match(/^\/api\/v1\/transactions\/(\d+)\/refunds$/)
    if (refundMatch && method === 'GET') {
      const originalId = Number(refundMatch[1])
      const original = state.transactions.find(
        (item) => Number(item.id) === originalId,
      )
      const refunds = state.transactions
        .filter((item) => item.adjustmentType === 'REFUND'
          && Number(item.reversesTransactionId) === originalId)
        .map((item) => ({
          id: item.id,
          amount: item.amount,
          occurredAt: item.occurredAt,
          memo: item.memo,
          version: item.version,
        }))
      const originalAmount = Number(original?.amount ?? 0)
      const refundedAmount = refunds.reduce(
        (sum, refund) => sum + Number(refund.amount),
        0,
      )
      return jsonResponse({
        originalTransactionId: originalId,
        originalAmount,
        refundedAmount,
        remainingRefundableAmount: originalAmount - refundedAmount,
        refunds,
      })
    }
    if (refundMatch && method === 'POST') {
      if (options.refundCreateGate) await options.refundCreateGate
      if (options.failRefundCreate) {
        return jsonResponse({
          code: 'TRANSACTION_REFUND_EXCEEDS_ORIGINAL',
          message: '환불 가능 금액을 초과했습니다.',
        }, 422)
      }
      const originalId = Number(refundMatch[1])
      const original = state.transactions.find(
        (item) => Number(item.id) === originalId,
      ) as ReturnType<typeof primaryTransaction>
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = refundTransaction({
        id: 700 + state.transactions.length,
        original,
        amount: Number(inputBody.amount),
        occurredAt: String(inputBody.occurredAt),
        memo: inputBody.memo == null ? null : String(inputBody.memo),
      })
      state.transactions.unshift(created)
      return jsonResponse(created, 201)
    }
    if (/^\/api\/v1\/transactions\/\d+$/.test(url.pathname) && method === 'PATCH') {
      const transactionId = Number(url.pathname.split('/').at(-1))
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const index = state.transactions.findIndex((item) => Number(item.id) === transactionId)
      const current = state.transactions[index]
      const updated = transactionResponse(
        inputBody,
        transactionId,
        Number(current?.version ?? 0) + 1,
      )
      state.transactions[index] = updated
      return jsonResponse(updated)
    }
    if (/^\/api\/v1\/transactions\/\d+$/.test(url.pathname) && method === 'DELETE') {
      const transactionId = Number(url.pathname.split('/').at(-1))
      state.transactions = state.transactions.filter((item) => Number(item.id) !== transactionId)
      return jsonResponse(null, 204)
    }

    return jsonResponse({ code: 'NOT_MOCKED', message: path }, 500)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, state }
}

function useCalendarUrl(search = '?month=2026-08&view=all&date=2026-08-27') {
  window.history.replaceState({}, '', `/${search}`)
}

function useBudgetUrl(month = '2026-08') {
  window.history.replaceState({}, '', `/?screen=budget&month=${month}`)
}

function useStatisticsUrl(search = 'preset=this-month&view=all') {
  window.history.replaceState({}, '', `/?screen=statistics&${search}`)
}

function useGoalUrl() {
  window.history.replaceState({}, '', '/?screen=goal')
}

describe('App', () => {
  it('renders authentication loading and stable error states', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))
    const { unmount } = render(<App />)
    expect(screen.getByRole('status')).toHaveTextContent('현재 사용자와 Household를 확인합니다.')
    unmount()

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 401)))
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('인증이 필요합니다.')
  })

  it('renders the unregistered Household state without starting Ledger requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({
      code: 'USER_NOT_REGISTERED',
    }, 403)))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('등록된 사용자가 아닙니다.')
    expect(screen.getByText(/내부 User와 Household membership/)).toBeInTheDocument()
  })

  it('renders the Couple-first sections in contract order with actual member names', async () => {
    useCalendarUrl()
    installLedgerRouter({
      transactions: [
        primaryTransaction({ id: 400, amount: 12_000 }),
        primaryTransaction({
          id: 401,
          amount: 5_000,
          occurredAt: '2026-07-27T03:00:00Z',
        }),
      ],
    })
    render(<App />)

    expect(await screen.findByRole('heading', { level: 1, name: '우리의 장부' }))
      .toBeInTheDocument()
    expect(screen.getAllByText('Owner').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Member').length).toBeGreaterThan(0)
    expect(screen.getByText(/테스트 Household · owner@example.test · OWNER/))
      .toBeInTheDocument()
    const hero = screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section')
    await waitFor(() => expect(hero).toHaveTextContent('12,000원'))
    expect(hero).toHaveTextContent('지난달보다 7,000원 더 썼어요.')
    expect(await screen.findByRole('heading', { name: '둘의 결혼자금 목표를 만들어 보세요' }))
      .toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Calendar 보기 범위' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '2026년 8월' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '8월 27일의 기록' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeInTheDocument()
  })

  it('renders actual Goal values and opens the accessible detail without a new bottom tab', async () => {
    useCalendarUrl()
    installLedgerRouter({ goal: marriageGoal() })
    render(<App />)

    const goalButton = await screen.findByRole('button', { name: /우리 집까지/ })
    expect(goalButton).toHaveTextContent('32,400,000원')
    expect(goalButton).toHaveTextContent('/ 100,000,000원')
    expect(goalButton).toHaveTextContent('32.4%')
    expect(goalButton).toHaveTextContent('이번 달 +1,800,000원')
    fireEvent.click(goalButton)

    expect(await screen.findByRole('heading', { name: '결혼자금' })).toBeInTheDocument()
    expect(window.location.search).toBe('?screen=goal')
    expect(screen.getByText('67,600,000원', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('2030년 6월 예상')).toBeInTheDocument()
    expect(screen.getByRole('table', { name: '최근 6개월 월별 순저축' }))
      .toHaveTextContent('2026년 3월')
    expect(screen.getByText('비상금 통장')).toBeInTheDocument()
    expect(screen.getByText('주거래 통장 → 비상금 통장')).toBeInTheDocument()
    expect(screen.getByText('반복')).toBeInTheDocument()
    expect(screen.queryByText(/목표에 돈 추가|기여금 추가|Goal 입금/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /자산준비 중/ })).toBeDisabled()
  })

  it('creates a Goal with a blank amount, prevents duplicate pending submit, and restores focus', async () => {
    useCalendarUrl()
    let releaseMutation!: () => void
    const mutationGate = new Promise<void>((resolve) => { releaseMutation = resolve })
    const { fetchMock } = installLedgerRouter({ goal: null, goalMutationGate: mutationGate })
    render(<App />)

    const opener = await screen.findByRole('button', { name: '결혼자금 목표 만들기' })
    fireEvent.click(opener)
    const name = screen.getByRole('textbox', { name: '목표 이름' })
    const amount = screen.getByRole('spinbutton', { name: '목표 금액' })
    expect(name).toHaveFocus()
    expect(amount).toHaveValue(null)
    fireEvent.change(name, { target: { value: '우리 보금자리' } })
    fireEvent.change(amount, { target: { value: '90000000' } })
    const form = screen.getByRole('button', { name: 'Goal 저장' }).closest('form')!
    fireEvent.submit(form)
    fireEvent.submit(form)

    const createCalls = fetchMock.mock.calls.filter(([input, init]) =>
      String(input).includes('/api/v1/goals/marriage')
      && !String(input).includes('/accounts/')
      && init?.method === 'POST')
    expect(createCalls).toHaveLength(1)
    expect(JSON.parse(String(createCalls[0][1]?.body))).toEqual({
      name: '우리 보금자리',
      targetAmount: 90_000_000,
    })

    releaseMutation()
    expect(await screen.findByRole('button', { name: /우리 보금자리/ })).toBeInTheDocument()

    const editOpener = screen.getByRole('button', { name: /우리 보금자리/ })
    fireEvent.click(editOpener)
    await screen.findByRole('heading', { name: '결혼자금' })
    const editButton = screen.getByRole('button', { name: '수정' })
    fireEvent.click(editButton)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(editButton).toHaveFocus())
  })

  it('keeps Goal create and stale edit inputs after stable server errors', async () => {
    useCalendarUrl()
    installLedgerRouter({ goal: null, failGoalCreate: true })
    const { unmount } = render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '결혼자금 목표 만들기' }))
    fireEvent.change(screen.getByRole('textbox', { name: '목표 이름' }), {
      target: { value: '실패해도 유지' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: '목표 금액' }), {
      target: { value: '50000000' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Goal 저장' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('결혼자금 목표가 이미 있어요')
    expect(screen.getByRole('textbox', { name: '목표 이름' })).toHaveValue('실패해도 유지')
    expect(screen.getByRole('spinbutton', { name: '목표 금액' })).toHaveValue(50_000_000)
    unmount()

    useGoalUrl()
    const { fetchMock } = installLedgerRouter({ goal: marriageGoal(), failGoalUpdate: true })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '수정' }))
    fireEvent.change(screen.getByRole('textbox', { name: '목표 이름' }), {
      target: { value: '충돌 입력 유지' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: '목표 금액' }), {
      target: { value: '110000000' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Goal 저장' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 변경이 먼저 저장됐어요')
    expect(screen.getByRole('textbox', { name: '목표 이름' })).toHaveValue('충돌 입력 유지')
    const patchCall = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith('/api/v1/goals/marriage') && init?.method === 'PATCH')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      version: 0,
      name: '충돌 입력 유지',
      targetAmount: 110_000_000,
    })
  })

  it('links and unlinks an eligible Account while preserving link selection on conflict', async () => {
    useGoalUrl()
    const emptyLinkedGoal = marriageGoal({
      currentAmount: 0,
      achievementRate: 0,
      remainingAmount: 100_000_000,
      linkedAccounts: [],
      recentSavingsActivities: [],
    })
    const { fetchMock } = installLedgerRouter({ goal: emptyLinkedGoal })
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '계좌 연결' }))
    const choice = screen.getByRole('radio', { name: /비상금 통장/ })
    expect(choice).toHaveFocus()
    fireEvent.click(choice)
    fireEvent.click(screen.getByRole('button', { name: '선택한 Account 연결' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByText('비상금 통장')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).endsWith('/api/v1/goals/marriage/accounts/201')
      && init?.method === 'POST')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '연결 해제' }))
    fireEvent.click(screen.getByRole('button', { name: '해제 확인' }))
    await waitFor(() => expect(screen.getByText('저축 Account를 연결해 주세요.'))
      .toBeInTheDocument())
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).endsWith('/api/v1/goals/marriage/accounts/201')
      && init?.method === 'DELETE')).toBe(true)

    cleanup()
    useGoalUrl()
    installLedgerRouter({ goal: emptyLinkedGoal, failGoalLink: true })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '계좌 연결' }))
    const failedChoice = screen.getByRole('radio', { name: /비상금 통장/ })
    fireEvent.click(failedChoice)
    fireEvent.click(screen.getByRole('button', { name: '선택한 Account 연결' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('다른 Goal에 먼저 연결됐어요')
    expect(failedChoice).toBeChecked()
  })

  it('clears stale Goal numbers while loading and restores Goal direct history state', async () => {
    useGoalUrl()
    let releaseRead!: () => void
    const readGate = new Promise<void>((resolve) => { releaseRead = resolve })
    installLedgerRouter({ goal: marriageGoal(), goalReadGate: readGate })
    render(<App />)

    expect(await screen.findByText('Goal 지표를 다시 계산하고 있어요.'))
      .toHaveAttribute('role', 'status')
    expect(screen.queryByText(/32,400,000원/)).not.toBeInTheDocument()
    releaseRead()
    expect(await screen.findByText('2030년 6월 예상')).toBeInTheDocument()

    window.history.pushState({}, '', '/?month=2026-08&view=all&date=2026-08-27')
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(await screen.findByRole('heading', { name: '이번 달 우리가 쓴 돈' }))
      .toBeInTheDocument()
    window.history.pushState({}, '', '/?screen=goal')
    window.dispatchEvent(new PopStateEvent('popstate'))
    expect(await screen.findByRole('heading', { name: '결혼자금' })).toBeInTheDocument()
  })

  it('shows the amount difference when previous-month spending is zero', async () => {
    useCalendarUrl()
    installLedgerRouter({
      transactions: [primaryTransaction({ id: 400, amount: 12_000 })],
    })
    render(<App />)

    const hero = await screen.findByRole('heading', { name: '이번 달 우리가 쓴 돈' })
    await waitFor(() => expect(hero.closest('section'))
      .toHaveTextContent('지난달보다 12,000원 더 썼어요.'))
  })

  it('applies ALL, each member, and SHARED to summary and selected-day requests', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter({
      transactions: [
        primaryTransaction({ id: 400, amount: 12_000 }),
        primaryTransaction({ id: 401, amount: 7000, ownerMemberId: 101 }),
        primaryTransaction({ id: 402, amount: 5000, scope: 'SHARED' }),
        transferTransaction(403),
      ],
    })
    render(<App />)
    const scope = await screen.findByRole('navigation', { name: 'Calendar 보기 범위' })

    fireEvent.click(within(scope).getByRole('button', { name: 'Owner · 나' }))
    await waitFor(() => expect(
      screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section'),
    ).toHaveTextContent('12,000원'))
    expect(window.location.search).toContain('view=member')
    expect(window.location.search).toContain('memberId=100')

    fireEvent.click(within(scope).getByRole('button', { name: 'Member' }))
    await waitFor(() => expect(
      screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section'),
    ).toHaveTextContent('7,000원'))

    fireEvent.click(within(scope).getByRole('button', { name: '공동' }))
    await waitFor(() => expect(
      screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section'),
    ).toHaveTextContent('5,000원'))
    expect(fetchMock.mock.calls.some(([input]) =>
      String(input).includes('scope=SHARED'))).toBe(true)
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/calendar/month?') && url.includes('scope=SHARED')
    })).toBe(true)
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?') && url.includes('scope=SHARED')
    })).toBe(true)

    fireEvent.click(within(scope).getByRole('button', { name: '전체' }))
    await waitFor(() => expect(
      screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section'),
    ).toHaveTextContent('24,000원'))
  })

  it('marks transfer-only past dates as no-spend and never marks future dates', async () => {
    useCalendarUrl()
    installLedgerRouter({ transactions: [transferTransaction(403)] })
    render(<App />)

    const transferDay = await screen.findByRole('button', {
      name: '27일, 거래 1건, 무지출',
    })
    expect(within(transferDay).getByLabelText('무지출')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '29일, 거래 없음' }))
      .not.toHaveTextContent('🐾')
    expect(await screen.findByText('계좌 이체')).toBeInTheDocument()
    expect(screen.getByText('↔ 3,000원')).toBeInTheDocument()
  })

  it('updates URL and selected-day API when a calendar date is selected', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    const dateButton = await screen.findByRole('button', { name: '26일, 거래 없음, 무지출' })

    fireEvent.click(dateButton)

    expect(await screen.findByRole('heading', { name: '8월 26일의 기록' })).toBeInTheDocument()
    expect(window.location.search).toContain('date=2026-08-26')
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('from=2026-08-26')
        && url.includes('to=2026-08-26')
    })).toBe(true))
  })

  it('moves months with buttons, clamps the selected day, and exposes today/selection state', async () => {
    useCalendarUrl('?month=2026-01&view=all&date=2026-01-31')
    installLedgerRouter()
    render(<App />)
    const selected = await screen.findByRole('button', { name: '31일, 거래 없음, 무지출' })
    expect(selected).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(screen.getByRole('button', { name: '다음 달' }))

    expect(await screen.findByRole('heading', { name: '2026년 2월' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '2월 28일의 기록' })).toBeInTheDocument()
    expect(window.location.search).toContain('month=2026-02')
    expect(window.location.search).toContain('date=2026-02-28')

    window.history.pushState({}, '', '/?month=2026-08&view=all&date=2026-08-27')
    fireEvent(window, new PopStateEvent('popstate'))
    const today = await screen.findByRole('button', {
      name: '28일, 오늘, 거래 없음, 무지출',
    })
    expect(today).toHaveAttribute('aria-current', 'date')
  })

  it('synchronizes Calendar state on popstate without adding a router dependency', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    await screen.findByRole('heading', { name: '2026년 8월' })

    window.history.pushState(
      {},
      '',
      '/?month=2026-07&view=member&date=2026-07-15&memberId=101',
    )
    fireEvent(window, new PopStateEvent('popstate'))

    expect(await screen.findByRole('heading', { name: '2026년 7월' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Member' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: '7월 15일의 기록' })).toBeInTheDocument()
  })

  it('opens Quick Entry on the selected date with current-user PERSONAL defaults', async () => {
    useCalendarUrl('?month=2026-08&view=shared&date=2026-08-27')
    installLedgerRouter()
    render(<App />)
    const trigger = await screen.findByRole('button', { name: '2026-08-27 빠른 입력 열기' })

    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    const amount = within(dialog).getByLabelText(/금액/)
    expect(amount).toHaveFocus()
    expect(amount).toHaveAttribute('inputmode', 'numeric')
    expect(within(dialog).getByLabelText('날짜')).toHaveValue('2026-08-27')
    expect(within(dialog).getByLabelText('범위')).toHaveValue('PERSONAL')
    expect(within(dialog).getByLabelText('Owner')).toHaveValue('100')
  })

  it('clears Category on actual type changes and preserves inputs for the same type', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /빠른 입력 열기/ }))
    const dialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    const category = within(dialog).getByLabelText('Category')
    const account = within(dialog).getByLabelText('Account')

    expect(category).toHaveValue('300')
    expect(account).toHaveValue('200')
    fireEvent.click(within(dialog).getByRole('button', { name: '지출' }))
    expect(category).toHaveValue('300')
    expect(account).toHaveValue('200')

    fireEvent.click(within(dialog).getByRole('button', { name: '수입' }))
    expect(category).toHaveValue('')
    fireEvent.change(category, { target: { value: '301' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '수입' }))
    expect(category).toHaveValue('301')
    expect(account).toHaveValue('200')

    fireEvent.click(within(dialog).getByRole('button', { name: '지출' }))
    expect(category).toHaveValue('')
  })

  it('closes Quick Entry with Escape and restores focus to its opener', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    const trigger = await screen.findByRole('button', { name: /빠른 입력 열기/ })
    fireEvent.click(trigger)
    await screen.findByRole('dialog', { name: '빠른 입력' })

    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '빠른 입력' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('closes Quick Entry on browser back state without losing Calendar context', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    const trigger = await screen.findByRole('button', { name: /빠른 입력 열기/ })
    fireEvent.click(trigger)
    await screen.findByRole('dialog', { name: '빠른 입력' })

    window.history.replaceState({}, '', window.location.href)
    fireEvent(window, new PopStateEvent('popstate'))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '빠른 입력' }))
      .not.toBeInTheDocument())
    expect(window.location.search).toContain('date=2026-08-27')
  })

  it('prevents duplicate submit, shows success, closes, and refreshes the same context', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /빠른 입력 열기/ }))
    const dialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    fireEvent.change(within(dialog).getByLabelText(/금액/), { target: { value: '12000' } })
    const submit = within(dialog).getByRole('button', { name: '거래 저장' })

    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(await within(dialog).findByRole('status')).toHaveTextContent('저장했어요 🐾')
    expect(fetchMock.mock.calls.filter(([input, init]) =>
      input === '/api/v1/transactions' && init?.method === 'POST')).toHaveLength(1)
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '빠른 입력' }))
      .not.toBeInTheDocument())
    expect(await screen.findByText('−12,000원')).toBeInTheDocument()
    expect(window.location.search).toContain('date=2026-08-27')
  })

  it('keeps Quick Entry and its input after a server validation failure', async () => {
    useCalendarUrl()
    installLedgerRouter({ failTransactionCreate: true })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /빠른 입력 열기/ }))
    const dialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    const amount = within(dialog).getByLabelText(/금액/)
    const memo = within(dialog).getByLabelText('메모 (선택)')
    fireEvent.change(amount, { target: { value: '15000' } })
    fireEvent.change(memo, { target: { value: '입력 유지' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '거래 저장' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('분류를 확인해 주세요.')
    expect(amount).toHaveValue(15000)
    expect(memo).toHaveValue('입력 유지')
    expect(dialog).toBeInTheDocument()
  })

  it('offers Refund only from a NORMAL EXPENSE and shows partial or full state', async () => {
    useCalendarUrl()
    const original = primaryTransaction({ id: 400, amount: 50_000 })
    const income = primaryTransaction({
      id: 401,
      amount: 100_000,
      type: 'INCOME',
    })
    const partialRefund = refundTransaction({
      id: 402,
      original,
      amount: 20_000,
    })
    installLedgerRouter({
      transactions: [original, income, transferTransaction(403), partialRefund],
    })
    render(<App />)

    const originalRow = (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    expect(await within(originalRow).findByText(
      '20,000원 환불됨 · 30,000원 환불 가능',
    )).toBeInTheDocument()
    expect(within(originalRow).getByRole('button', { name: '환불' })).toBeInTheDocument()
    expect(within((screen.getByText('+100,000원').closest('li') as HTMLElement))
      .queryByRole('button', { name: '환불' })).not.toBeInTheDocument()
    expect(within((screen.getByText('↔ 3,000원').closest('li') as HTMLElement))
      .queryByRole('button', { name: '환불' })).not.toBeInTheDocument()
    const refundRow = screen.getByText('식비 환불').closest('li') as HTMLElement
    expect(within(refundRow).queryByRole('button', { name: '환불' }))
      .not.toBeInTheDocument()

    cleanup()
    installLedgerRouter({
      transactions: [
        original,
        refundTransaction({ id: 404, original, amount: 50_000 }),
      ],
    })
    render(<App />)
    const fullyRefundedOriginal =
      (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    expect(await within(fullyRefundedOriginal).findByText('전액 환불됨'))
      .toBeInTheDocument()
    expect(within(fullyRefundedOriginal).queryByRole('button', { name: '환불' }))
      .not.toBeInTheDocument()
  })

  it('opens Refund with inherited context and restores focus after Escape', async () => {
    useCalendarUrl()
    const original = primaryTransaction({ id: 400, amount: 50_000 })
    installLedgerRouter({
      transactions: [
        original,
        refundTransaction({ id: 401, original, amount: 20_000 }),
      ],
    })
    render(<App />)
    const originalRow = (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    const trigger = await within(originalRow).findByRole('button', { name: '환불' })

    fireEvent.click(trigger)

    const dialog = await screen.findByRole('dialog', { name: '환불 처리' })
    expect(within(dialog).getByText('식비 · 50,000원')).toBeInTheDocument()
    expect(within(dialog).getByText('주거래 통장')).toBeInTheDocument()
    expect(within(dialog).getByText('20,000원')).toBeInTheDocument()
    expect(within(dialog).getByText('30,000원')).toBeInTheDocument()
    const amount = within(dialog).getByLabelText('환불 금액')
    expect(amount).toHaveFocus()
    expect(amount).toHaveAttribute('max', '30000')
    expect(within(dialog).getByLabelText('날짜')).toHaveValue('2026-08-28')
    expect(within(dialog).queryByLabelText('범위')).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Category')).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Account')).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '환불 처리' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())

    fireEvent.click(trigger)
    const reopenedDialog = await screen.findByRole('dialog', { name: '환불 처리' })
    fireEvent.mouseDown(reopenedDialog.parentElement as HTMLElement)

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '환불 처리' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('prevents duplicate Refund submit and refreshes Calendar after success', async () => {
    useCalendarUrl()
    let releaseRefund!: () => void
    const refundCreateGate = new Promise<void>((resolve) => {
      releaseRefund = resolve
    })
    const original = primaryTransaction({ id: 400, amount: 50_000 })
    const { fetchMock } = installLedgerRouter({
      transactions: [original],
      refundCreateGate,
    })
    render(<App />)
    const originalRow = (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    fireEvent.click(await within(originalRow).findByRole('button', { name: '환불' }))
    const dialog = await screen.findByRole('dialog', { name: '환불 처리' })
    const amount = within(dialog).getByLabelText('환불 금액')
    fireEvent.change(amount, { target: { value: '30000' } })
    const submit = within(dialog).getByRole('button', { name: '30,000원 환불 기록' })

    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(await within(dialog).findByRole('button', { name: '환불 기록 중…' }))
      .toBeDisabled()
    expect(fetchMock.mock.calls.filter(([input, init]) =>
      input === '/api/v1/transactions/400/refunds'
        && init?.method === 'POST')).toHaveLength(1)
    releaseRefund()
    expect(await within(dialog).findByRole('status')).toHaveTextContent('환불을 기록했어요')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '환불 처리' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(
      screen.getByRole('heading', { name: '이번 달 우리가 쓴 돈' }).closest('section'),
    ).toHaveTextContent('20,000원'))
    const refreshedOriginal =
      (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    const refreshedRefundButton = await within(refreshedOriginal)
      .findByRole('button', { name: '환불' })
    await waitFor(() => expect(refreshedRefundButton).toHaveFocus())
    fireEvent.click(await screen.findByRole('button', {
      name: '28일, 오늘, 거래 1건',
    }))
    expect(await screen.findByText('+30,000원')).toBeInTheDocument()
  })

  it('keeps Refund inputs after client or server cap errors', async () => {
    useCalendarUrl()
    const original = primaryTransaction({ id: 400, amount: 50_000 })
    const { fetchMock } = installLedgerRouter({
      transactions: [
        original,
        refundTransaction({ id: 401, original, amount: 20_000 }),
      ],
      failRefundCreate: true,
    })
    render(<App />)
    const originalRow = (await screen.findByText('−50,000원')).closest('li') as HTMLElement
    fireEvent.click(await within(originalRow).findByRole('button', { name: '환불' }))
    const dialog = await screen.findByRole('dialog', { name: '환불 처리' })
    const amount = within(dialog).getByLabelText('환불 금액')
    const memo = within(dialog).getByLabelText('메모 (선택)')

    fireEvent.change(amount, { target: { value: '40000' } })
    fireEvent.change(memo, { target: { value: '입력 유지' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '40,000원 환불 기록' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '환불 가능 금액은 30,000원입니다.',
    )
    expect(fetchMock.mock.calls.filter(([input, init]) =>
      input === '/api/v1/transactions/400/refunds'
        && init?.method === 'POST')).toHaveLength(0)

    fireEvent.change(amount, { target: { value: '30000' } })
    fireEvent.click(within(dialog).getByRole('button', { name: '30,000원 환불 기록' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      '환불 가능 금액을 초과했습니다.',
    )
    expect(amount).toHaveValue(30000)
    expect(memo).toHaveValue('입력 유지')
    expect(dialog).toBeInTheDocument()
  })

  it('removes generic edit from Refund and confirms deletion before refresh', async () => {
    useCalendarUrl()
    const original = primaryTransaction({ id: 400, amount: 50_000 })
    const refund = refundTransaction({ id: 401, original, amount: 20_000 })
    const { fetchMock } = installLedgerRouter({ transactions: [original, refund] })
    render(<App />)
    const refundRow = (await screen.findByText('식비 환불')).closest('li') as HTMLElement
    expect(within(refundRow).getByText('+20,000원')).toBeInTheDocument()
    expect(within(refundRow).getByText('부분 환불 · 주거래 통장')).toBeInTheDocument()
    expect(within(refundRow).getByText('원 지출을 상쇄한 환불 기록'))
      .toBeInTheDocument()
    expect(within(refundRow).queryByRole('button', { name: '수정' }))
      .not.toBeInTheDocument()

    fireEvent.click(within(refundRow).getByRole('button', { name: '삭제' }))
    expect(within(refundRow).getByText('환불 기록만 삭제되며 원 지출은 유지됩니다.'))
      .toBeInTheDocument()
    expect(screen.getByText('+20,000원')).toBeInTheDocument()
    fireEvent.click(within(refundRow).getByRole('button', { name: '삭제 확인' }))

    await waitFor(() => expect(screen.queryByText('+20,000원')).not.toBeInTheDocument())
    expect(screen.getByText('−50,000원')).toBeInTheDocument()
    expect(await screen.findByText('50,000원 환불 가능')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).startsWith('/api/v1/transactions/401?version=')
        && init?.method === 'DELETE')).toBe(true)
  })

  it('edits and deletes a selected-day transaction and refreshes month and day', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter({
      transactions: [primaryTransaction({ id: 400, amount: 12_000 })],
    })
    render(<App />)
    const selectedDay = (await screen.findByRole('heading', { name: '8월 27일의 기록' }))
      .closest('section') as HTMLElement

    fireEvent.click(await within(selectedDay).findByRole('button', { name: '수정' }))
    const editDialog = await screen.findByRole('dialog', { name: '거래 수정' })
    fireEvent.change(within(editDialog).getByLabelText(/금액/), { target: { value: '20000' } })
    fireEvent.click(within(editDialog).getByRole('button', { name: '수정 저장' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '거래 수정' }))
      .not.toBeInTheDocument())
    expect(await screen.findByText('−20,000원')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/transactions/400' && init?.method === 'PATCH')).toBe(true)

    fireEvent.click(within(selectedDay).getByRole('button', { name: '삭제' }))
    expect(await screen.findByText('이 날짜에는 아직 거래가 없어요.')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).startsWith('/api/v1/transactions/400?version=')
        && init?.method === 'DELETE')).toBe(true)
  })

  it('keeps account and category management behind the settings entry', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })

    fireEvent.change(within(settings).getByLabelText('계좌 이름'), {
      target: { value: '생활비 통장' },
    })
    fireEvent.click(within(settings).getByRole('button', { name: '계좌 추가' }))
    expect((await within(settings).findAllByText('생활비 통장')).length).toBeGreaterThan(0)

    fireEvent.change(within(settings).getByLabelText('Group 이름'), {
      target: { value: '생활' },
    })
    fireEvent.click(within(settings).getByRole('button', { name: 'Group 추가' }))
    expect((await within(settings).findAllByText('생활')).length).toBeGreaterThan(0)
    expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/accounts' && init?.method === 'POST')).toBe(true)
  })

  it('manages active paused and ended recurring rules inside Settings', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter({
      recurringTransactions: [
        recurringRule(),
        recurringRule({ id: 801, name: 'OTT 구독', active: false, status: 'PAUSED' }),
        recurringRule({
          id: 802,
          name: '종료 보험',
          nextRecurrenceDate: null,
          status: 'ENDED',
        }),
      ],
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })

    expect(await within(settings).findByRole('heading', { name: '반복 거래' }))
      .toBeInTheDocument()
    expect(within(settings).getByText('월급')).toBeInTheDocument()
    expect(within(settings).getByText('OTT 구독')).toBeInTheDocument()
    expect(within(settings).getByText('종료 보험')).toBeInTheDocument()
    expect(within(settings).getByText('활성')).toBeInTheDocument()
    expect(within(settings).getByText('중지됨')).toBeInTheDocument()
    expect(within(settings).getByText('종료됨')).toBeInTheDocument()
    expect(within(settings).getByText(/중지 기간은 소급 생성하지 않습니다/))
      .toBeInTheDocument()

    fireEvent.click(within(settings).getAllByRole('button', { name: '중지' })[0])
    await within(settings).findAllByText('중지됨')
    fireEvent.click(within(settings).getAllByRole('button', { name: '재개' })[0])
    await within(settings).findByText('활성')
    expect(fetchMock.mock.calls.filter(([input, init]) =>
      String(input) === '/api/v1/recurring-transactions/800'
        && init?.method === 'PATCH')).toHaveLength(2)
  })

  it('creates and edits a recurring rule with schedule fields and focus lifecycle', async () => {
    useCalendarUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })
    const addButton = await within(settings).findByRole('button', { name: '+ 반복 거래 추가' })
    fireEvent.click(addButton)

    const createDialog = await screen.findByRole('dialog', { name: '반복 거래 추가' })
    const nameInput = within(createDialog).getByLabelText('이름')
    await waitFor(() => expect(nameInput).toHaveFocus())
    fireEvent.change(nameInput, { target: { value: '격주 생활비' } })
    fireEvent.change(within(createDialog).getByLabelText('금액'), {
      target: { value: '45000' },
    })
    fireEvent.change(within(createDialog).getByLabelText('주기'), {
      target: { value: 'WEEKLY' },
    })
    fireEvent.change(within(createDialog).getByLabelText('간격'), {
      target: { value: '2' },
    })
    fireEvent.change(within(createDialog).getByLabelText('실행 시간'), {
      target: { value: '08:30' },
    })
    fireEvent.click(within(createDialog).getByRole('button', { name: '반복 거래 저장' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '반복 거래 추가' }))
      .not.toBeInTheDocument())
    expect(addButton).toHaveFocus()
    expect(within(settings).getByText('격주 생활비')).toBeInTheDocument()
    const createCall = fetchMock.mock.calls.find(([input, init]) =>
      input === '/api/v1/recurring-transactions' && init?.method === 'POST')
    const payload = JSON.parse(String(createCall?.[1]?.body)) as Record<string, unknown>
    expect(payload).toMatchObject({
      type: 'EXPENSE',
      frequency: 'WEEKLY',
      intervalValue: 2,
      startDate: '2026-08-28',
      scheduledLocalTime: '08:30',
      autoPost: true,
    })
    expect(payload).not.toHaveProperty('householdId')
    expect(payload).not.toHaveProperty('adjustmentType')

    const row = within(settings).getByText('격주 생활비').closest('li') as HTMLElement
    const editButton = within(row).getByRole('button', { name: '수정' })
    fireEvent.click(editButton)
    const editDialog = await screen.findByRole('dialog', { name: '반복 거래 수정' })
    expect(within(editDialog).getByText(/이미 생성된 거래는 바뀌지 않습니다/))
      .toBeInTheDocument()
    expect(within(editDialog).queryByText('월말')).not.toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(editButton).toHaveFocus())
  })

  it('keeps the full EXPENSE template when the active recurring type is clicked again', async () => {
    useCalendarUrl()
    const insuranceCategory = {
      ...expenseCategory,
      id: 302,
      name: '보험',
      sortOrder: 1,
    }
    const cardAccount = {
      ...checkingAccount,
      id: 202,
      name: '생활 카드',
      type: 'CREDIT_CARD',
      nature: 'LIABILITY',
      sortOrder: 2,
    }
    const expenseRule = recurringRule({
      name: '보험료',
      type: 'EXPENSE',
      amount: 120_000,
      owner: { memberId: 101, displayName: 'Member' },
      payer: { memberId: 101, displayName: 'Member' },
      category: { id: insuranceCategory.id, name: insuranceCategory.name, archived: false },
      accounts: [{ role: 'PRIMARY', account: cardAccount }],
      memo: '보험 메모',
    })
    const { fetchMock } = installLedgerRouter({
      accounts: [checkingAccount, savingsAccount, cardAccount],
      categories: [expenseCategory, insuranceCategory, incomeCategory],
      recurringTransactions: [expenseRule],
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })
    const row = (await within(settings).findByText('보험료')).closest('li') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: '수정' }))
    const dialog = await screen.findByRole('dialog', { name: '반복 거래 수정' })

    fireEvent.click(within(dialog).getByRole('button', { name: '지출' }))

    expect(within(dialog).getByLabelText('Category')).toHaveValue('302')
    expect(within(dialog).getByLabelText('Account')).toHaveValue('202')
    expect(within(dialog).getByLabelText('Owner')).toHaveValue('101')
    expect(within(dialog).getByLabelText('Payer (선택)')).toHaveValue('101')
    fireEvent.click(within(dialog).getByRole('button', { name: '반복 거래 수정' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')).toBe(true))
    const patchCall = fetchMock.mock.calls.find(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      version: 0,
      name: '보험료',
      type: 'EXPENSE',
      amount: 120_000,
      scope: 'PERSONAL',
      ownerMemberId: 101,
      payerMemberId: 101,
      categoryId: 302,
      accountId: 202,
      sourceAccountId: null,
      destinationAccountId: null,
      memo: '보험 메모',
    })
  })

  it('keeps the full INCOME template when the active recurring type is clicked again', async () => {
    useCalendarUrl()
    const bonusCategory = {
      ...incomeCategory,
      id: 303,
      name: '보너스',
      sortOrder: 1,
    }
    const incomeRule = recurringRule({
      name: '성과급',
      amount: 500_000,
      owner: { memberId: 101, displayName: 'Member' },
      category: { id: bonusCategory.id, name: bonusCategory.name, archived: false },
      accounts: [{ role: 'PRIMARY', account: savingsAccount }],
      memo: '성과급 메모',
    })
    const { fetchMock } = installLedgerRouter({
      categories: [expenseCategory, incomeCategory, bonusCategory],
      recurringTransactions: [incomeRule],
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })
    const row = (await within(settings).findByText('성과급')).closest('li') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: '수정' }))
    const dialog = await screen.findByRole('dialog', { name: '반복 거래 수정' })

    fireEvent.click(within(dialog).getByRole('button', { name: '수입' }))

    expect(within(dialog).getByLabelText('Category')).toHaveValue('303')
    expect(within(dialog).getByLabelText('Account')).toHaveValue('201')
    expect(within(dialog).getByLabelText('Owner')).toHaveValue('101')
    fireEvent.click(within(dialog).getByRole('button', { name: '반복 거래 수정' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')).toBe(true))
    const patchCall = fetchMock.mock.calls.find(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      version: 0,
      name: '성과급',
      type: 'INCOME',
      amount: 500_000,
      scope: 'PERSONAL',
      ownerMemberId: 101,
      payerMemberId: null,
      categoryId: 303,
      accountId: 201,
      sourceAccountId: null,
      destinationAccountId: null,
      memo: '성과급 메모',
    })
  })

  it('keeps TRANSFER source and destination when the active recurring type is clicked again', async () => {
    useCalendarUrl()
    const destinationAccount = {
      ...checkingAccount,
      id: 202,
      name: '목적 통장',
      sortOrder: 2,
    }
    const transferRule = recurringRule({
      name: '저축 이체',
      type: 'TRANSFER',
      amount: 300_000,
      scope: null,
      owner: null,
      payer: null,
      category: null,
      accounts: [
        { role: 'SOURCE', account: savingsAccount },
        { role: 'DESTINATION', account: destinationAccount },
      ],
      memo: '이체 메모',
    })
    const { fetchMock } = installLedgerRouter({
      accounts: [checkingAccount, savingsAccount, destinationAccount],
      recurringTransactions: [transferRule],
    })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    const settings = await screen.findByRole('dialog', { name: '장부 설정' })
    const row = (await within(settings).findByText('저축 이체')).closest('li') as HTMLElement
    fireEvent.click(within(row).getByRole('button', { name: '수정' }))
    const dialog = await screen.findByRole('dialog', { name: '반복 거래 수정' })

    fireEvent.click(within(dialog).getByRole('button', { name: '이체' }))

    expect(within(dialog).getByLabelText('출금 Account')).toHaveValue('201')
    expect(within(dialog).getByLabelText('입금 Account')).toHaveValue('202')
    fireEvent.click(within(dialog).getByRole('button', { name: '반복 거래 수정' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')).toBe(true))
    const patchCall = fetchMock.mock.calls.find(([input, init]) =>
      input === '/api/v1/recurring-transactions/800' && init?.method === 'PATCH')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      version: 0,
      name: '저축 이체',
      type: 'TRANSFER',
      amount: 300_000,
      scope: null,
      ownerMemberId: null,
      payerMemberId: null,
      categoryId: null,
      accountId: null,
      sourceAccountId: 201,
      destinationAccountId: 202,
      memo: '이체 메모',
    })
  })

  it('keeps recurring form input on failure and prevents duplicate pending submits', async () => {
    useCalendarUrl()
    let releaseGate: (() => void) | undefined
    const gate = new Promise<void>((resolve) => { releaseGate = resolve })
    const { fetchMock } = installLedgerRouter({ recurringCreateGate: gate })
    const { unmount } = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    fireEvent.click(await screen.findByRole('button', { name: '+ 반복 거래 추가' }))
    const pendingDialog = await screen.findByRole('dialog', { name: '반복 거래 추가' })
    fireEvent.change(within(pendingDialog).getByLabelText('이름'), {
      target: { value: '월 구독' },
    })
    fireEvent.change(within(pendingDialog).getByLabelText('금액'), {
      target: { value: '17000' },
    })
    const submit = within(pendingDialog).getByRole('button', { name: '반복 거래 저장' })
    fireEvent.click(submit)
    fireEvent.click(submit)
    await waitFor(() => expect(fetchMock.mock.calls.filter(([input, init]) =>
      input === '/api/v1/recurring-transactions' && init?.method === 'POST')).toHaveLength(1))
    expect(within(pendingDialog).getByRole('button', { name: '저장 중…' })).toBeDisabled()
    releaseGate?.()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '반복 거래 추가' }))
      .not.toBeInTheDocument())
    unmount()

    installLedgerRouter({ failRecurringCreate: true })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '설정' }))
    fireEvent.click(await screen.findByRole('button', { name: '+ 반복 거래 추가' }))
    const failedDialog = await screen.findByRole('dialog', { name: '반복 거래 추가' })
    const failedName = within(failedDialog).getByLabelText('이름')
    const failedAmount = within(failedDialog).getByLabelText('금액')
    fireEvent.change(failedName, { target: { value: '실패 구독' } })
    fireEvent.change(failedAmount, { target: { value: '19000' } })
    fireEvent.click(within(failedDialog).getByRole('button', { name: '반복 거래 저장' }))
    expect(await within(failedDialog).findByRole('alert'))
      .toHaveTextContent('반복 일정을 확인해 주세요.')
    expect(failedName).toHaveValue('실패 구독')
    expect(failedAmount).toHaveValue(19000)
  })

  it('keeps Budget and Statistics active while Assets remains disabled', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    const navigation = await screen.findByRole('navigation', { name: '주요 메뉴' })

    expect(within(navigation).getByRole('button', { name: /Calendar/ }))
      .toHaveAttribute('aria-current', 'page')
    expect(within(navigation).getByRole('button', { name: /예산/ })).not.toBeDisabled()
    expect(within(navigation).getByRole('button', { name: /통계/ })).not.toBeDisabled()
    expect(within(navigation).getByRole('button', { name: /자산/ })).toBeDisabled()
  })

  it('renders actual Budget scope cards and distinguishes unset, zero, and overrun states', async () => {
    useCalendarUrl('?month=2026-07&view=all&date=2026-07-27')
    installLedgerRouter({
      transactions: [
        primaryTransaction({ id: 400, amount: 12_000 }),
        primaryTransaction({ id: 401, amount: 7000, ownerMemberId: 101 }),
        primaryTransaction({ id: 402, amount: 5000, scope: 'SHARED' }),
      ],
      budgets: [
        {
          id: 600,
          month: '2026-08',
          scope: 'HOUSEHOLD',
          ownerMemberId: null,
          categoryId: null,
          amount: 20_000,
          version: 0,
        },
        {
          id: 601,
          month: '2026-08',
          scope: 'PERSONAL',
          ownerMemberId: 100,
          categoryId: null,
          amount: 0,
          version: 0,
        },
        {
          id: 602,
          month: '2026-08',
          scope: 'SHARED',
          ownerMemberId: null,
          categoryId: 300,
          amount: 0,
          version: 0,
        },
      ],
    })
    render(<App />)
    const navigation = await screen.findByRole('navigation', { name: '주요 메뉴' })

    fireEvent.click(within(navigation).getByRole('button', { name: /예산/ }))

    expect(await screen.findByRole('heading', { name: '예산' })).toBeInTheDocument()
    expect(within(navigation).getByRole('button', { name: /예산/ }))
      .toHaveAttribute('aria-current', 'page')
    expect(window.location.search).toBe('?screen=budget&month=2026-08')
    const householdCard = screen.getByRole('heading', { name: '우리 전체' })
      .closest('article') as HTMLElement
    expect(householdCard).toHaveTextContent('예산20,000원')
    expect(householdCard).toHaveTextContent('사용24,000원')
    expect(householdCard).toHaveTextContent('예산을 4,000원 초과했어요.')
    const ownerCard = screen.getByRole('heading', { name: 'Owner' })
      .closest('article') as HTMLElement
    expect(ownerCard).toHaveTextContent('예산0원')
    expect(ownerCard).toHaveTextContent('0원 예산을 초과했어요.')
    const partnerCard = screen.getByRole('heading', { name: 'Member' })
      .closest('article') as HTMLElement
    expect(partnerCard).toHaveTextContent('예산 미설정')
    expect(partnerCard).toHaveTextContent('이번 달 사용 7,000원')
    const categorySection = screen.getByRole('heading', { name: 'Category 예산' })
      .closest('section') as HTMLElement
    expect(categorySection).toHaveTextContent('식비')
    expect(categorySection).toHaveTextContent('0원 예산을 초과했어요.')
  })

  it('keeps an archived Category Budget visible without offering it for a new Budget', async () => {
    useBudgetUrl()
    installLedgerRouter({
      categories: [{ ...expenseCategory, archived: true }, incomeCategory],
      budgets: [{
        id: 600,
        month: '2026-08',
        scope: 'PERSONAL',
        ownerMemberId: 100,
        categoryId: 300,
        amount: 20_000,
        version: 0,
      }],
    })
    render(<App />)

    const categorySection = (await screen.findByRole('heading', { name: 'Category 예산' }))
      .closest('section') as HTMLElement
    expect(categorySection).toHaveTextContent('식비보관됨')

    const categoryRow = within(categorySection).getByText('식비').closest('li') as HTMLElement
    fireEvent.click(within(categoryRow).getByRole('button', { name: '수정' }))
    const editDialog = await screen.findByRole('dialog', { name: '예산 수정' })
    expect(within(editDialog).getByRole('option', { name: '식비 · 보관됨' })).toBeInTheDocument()
    expect(within(editDialog).getByRole('button', { name: '예산 저장' })).toBeDisabled()
    fireEvent.click(within(editDialog).getByRole('button', { name: '예산 입력 닫기' }))

    fireEvent.click(screen.getByRole('button', { name: '+ 예산 추가' }))
    const createDialog = await screen.findByRole('dialog', { name: '예산 추가' })
    expect(within(createDialog).queryByRole('option', { name: /식비/ })).not.toBeInTheDocument()
  })

  it('moves focus into the Budget Sheet and restores it to the opener after close', async () => {
    useBudgetUrl()
    installLedgerRouter()
    render(<App />)
    const opener = await screen.findByRole('button', { name: '+ 예산 추가' })

    fireEvent.click(opener)

    const dialog = await screen.findByRole('dialog', { name: '예산 추가' })
    expect(within(dialog).getByLabelText('예산 금액')).toHaveFocus()
    fireEvent.click(within(dialog).getByRole('button', { name: '예산 입력 닫기' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '예산 추가' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('keeps Budget month and destination in history and uses today for Budget Quick Entry', async () => {
    useBudgetUrl('2026-07')
    installLedgerRouter()
    render(<App />)

    expect(await screen.findByRole('heading', { name: '2026년 7월' })).toBeInTheDocument()
    const quickEntry = screen.getByRole('button', { name: '2026-08-28 빠른 입력 열기' })
    fireEvent.click(quickEntry)
    const quickEntryDialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    expect(within(quickEntryDialog).getByLabelText('날짜')).toHaveValue('2026-08-28')
    fireEvent.click(within(quickEntryDialog).getByRole('button', { name: '빠른 입력 닫기' }))

    fireEvent.click(screen.getByRole('button', { name: '예산 다음 달' }))
    expect(await screen.findByRole('heading', { name: '2026년 8월' })).toBeInTheDocument()
    expect(window.location.search).toBe('?screen=budget&month=2026-08')

    window.history.pushState({}, '', '/?screen=budget&month=2026-06')
    fireEvent(window, new PopStateEvent('popstate'))
    expect(await screen.findByRole('heading', { name: '2026년 6월' })).toBeInTheDocument()

    const navigation = screen.getByRole('navigation', { name: '주요 메뉴' })
    fireEvent.click(within(navigation).getByRole('button', { name: /Calendar/ }))
    expect(await screen.findByRole('navigation', { name: 'Calendar 보기 범위' }))
      .toBeInTheDocument()
    expect(within(navigation).getByRole('button', { name: /Calendar/ }))
      .toHaveAttribute('aria-current', 'page')
  })

  it('canonicalizes invalid direct and popstate Budget month URLs', async () => {
    useBudgetUrl('2026-13')
    installLedgerRouter()
    render(<App />)

    expect(await screen.findByRole('heading', { name: '2026년 8월' })).toBeInTheDocument()
    await waitFor(() => expect(window.location.search)
      .toBe('?screen=budget&month=2026-08'))

    window.history.pushState({}, '', '/?screen=budget&month=invalid')
    fireEvent(window, new PopStateEvent('popstate'))
    await waitFor(() => expect(window.location.search)
      .toBe('?screen=budget&month=2026-08'))
    expect(screen.getByRole('heading', { name: '2026년 8월' })).toBeInTheDocument()
  })

  it('creates a Budget, refreshes the same month, and offers only EXPENSE Categories', async () => {
    useBudgetUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    const householdCard = (await screen.findByRole('heading', { name: '우리 전체' }))
      .closest('article') as HTMLElement

    fireEvent.click(within(householdCard).getByRole('button', { name: '설정' }))
    const dialog = await screen.findByRole('dialog', { name: '예산 추가' })
    const categoryPicker = within(dialog).getByLabelText('Category')
    expect(within(categoryPicker).getByRole('option', { name: '식비' })).toBeInTheDocument()
    expect(within(categoryPicker).queryByRole('option', { name: '급여' })).not.toBeInTheDocument()
    fireEvent.change(within(dialog).getByLabelText('예산 금액'), {
      target: { value: '50000' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: '예산 저장' }))

    await waitFor(() => expect(householdCard).toHaveTextContent('예산50,000원'))
    expect(window.location.search).toBe('?screen=budget&month=2026-08')
    expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/budgets' && init?.method === 'POST')).toBe(true)
  })

  it('prevents a second Budget submit while the first request is pending', async () => {
    useBudgetUrl()
    let releaseBudgetCreate!: () => void
    const budgetCreateGate = new Promise<void>((resolve) => {
      releaseBudgetCreate = resolve
    })
    const { fetchMock } = installLedgerRouter({ budgetCreateGate })
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '+ 예산 추가' }))
    const dialog = await screen.findByRole('dialog', { name: '예산 추가' })
    fireEvent.change(within(dialog).getByLabelText('예산 금액'), {
      target: { value: '50000' },
    })
    const form = within(dialog).getByRole('button', { name: '예산 저장' })
      .closest('form') as HTMLFormElement

    fireEvent.submit(form)
    fireEvent.submit(form)

    expect(fetchMock.mock.calls.filter(([input, init]) =>
      input === '/api/v1/budgets' && init?.method === 'POST')).toHaveLength(1)
    expect(within(dialog).getByRole('button', { name: '저장 중…' })).toBeDisabled()

    releaseBudgetCreate()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '예산 추가' }))
      .not.toBeInTheDocument())
  })

  it('updates and deletes only the Budget row while preserving calculated spending', async () => {
    useBudgetUrl()
    const { fetchMock } = installLedgerRouter({
      transactions: [primaryTransaction({ id: 400, amount: 12_000, scope: 'SHARED' })],
      budgets: [{
        id: 600,
        month: '2026-08',
        scope: 'HOUSEHOLD',
        ownerMemberId: null,
        categoryId: null,
        amount: 15_000,
        version: 0,
      }],
    })
    render(<App />)
    const householdCard = (await screen.findByRole('heading', { name: '우리 전체' }))
      .closest('article') as HTMLElement

    fireEvent.click(within(householdCard).getByRole('button', { name: '수정' }))
    const editDialog = await screen.findByRole('dialog', { name: '예산 수정' })
    fireEvent.change(within(editDialog).getByLabelText('예산 금액'), {
      target: { value: '20000' },
    })
    fireEvent.click(within(editDialog).getByRole('button', { name: '예산 저장' }))

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '예산 수정' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(householdCard).toHaveTextContent('20,000원'))
    expect(fetchMock.mock.calls.some(([input, init]) =>
      input === '/api/v1/budgets/600' && init?.method === 'PATCH')).toBe(true)

    fireEvent.click(within(householdCard).getByRole('button', { name: '수정' }))
    const deleteDialog = await screen.findByRole('dialog', { name: '예산 수정' })
    fireEvent.click(within(deleteDialog).getByRole('button', { name: '예산 삭제' }))
    expect(within(deleteDialog).getByRole('alert')).toHaveTextContent(
      '2026년 8월 · 우리 전체 · 전체 Category 예산만 삭제할까요?',
    )
    fireEvent.click(within(deleteDialog).getByRole('button', { name: '삭제 확인' }))

    await waitFor(() => expect(householdCard).toHaveTextContent('예산 미설정'))
    expect(householdCard).toHaveTextContent('이번 달 사용 12,000원')
    expect(fetchMock.mock.calls.some(([input, init]) =>
      String(input).startsWith('/api/v1/budgets/600?version=1')
        && init?.method === 'DELETE')).toBe(true)
  })

  it('keeps Budget form values and shows stable duplicate and stale errors', async () => {
    useBudgetUrl()
    installLedgerRouter({ failBudgetCreate: true })
    const { unmount } = render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: '+ 예산 추가' }))
    const createDialog = await screen.findByRole('dialog', { name: '예산 추가' })
    fireEvent.change(within(createDialog).getByLabelText('범위'), {
      target: { value: 'PERSONAL:100' },
    })
    fireEvent.change(within(createDialog).getByLabelText('Category'), {
      target: { value: '300' },
    })
    const createAmount = within(createDialog).getByLabelText('예산 금액')
    fireEvent.change(createAmount, { target: { value: '300000' } })
    fireEvent.click(within(createDialog).getByRole('button', { name: '예산 저장' }))

    expect(await within(createDialog).findByRole('alert'))
      .toHaveTextContent('같은 월·범위·Category의 예산이 이미 있어요.')
    expect(createAmount).toHaveValue(300000)
    expect(within(createDialog).getByLabelText('범위')).toHaveValue('PERSONAL:100')
    expect(within(createDialog).getByLabelText('Category')).toHaveValue('300')
    unmount()

    installLedgerRouter({
      failBudgetUpdate: true,
      budgets: [{
        id: 600,
        month: '2026-08',
        scope: 'HOUSEHOLD',
        ownerMemberId: null,
        categoryId: null,
        amount: 100_000,
        version: 0,
      }],
    })
    render(<App />)
    const householdCard = (await screen.findByRole('heading', { name: '우리 전체' }))
      .closest('article') as HTMLElement
    fireEvent.click(within(householdCard).getByRole('button', { name: '수정' }))
    const updateDialog = await screen.findByRole('dialog', { name: '예산 수정' })
    const updateAmount = within(updateDialog).getByLabelText('예산 금액')
    fireEvent.change(updateAmount, { target: { value: '120000' } })
    fireEvent.click(within(updateDialog).getByRole('button', { name: '예산 저장' }))
    expect(await within(updateDialog).findByRole('alert'))
      .toHaveTextContent('다른 변경이 먼저 저장됐어요.')
    expect(updateAmount).toHaveValue(120000)
  })

  it('reuses the EXPENSE transaction filter for Budget drill-down including refunds', async () => {
    useBudgetUrl()
    const normal = primaryTransaction({ id: 400, amount: 12_000 })
    const refund = {
      ...primaryTransaction({ id: 401, amount: 2000, memo: '부분 환불' }),
      adjustmentType: 'REFUND',
    }
    const { fetchMock } = installLedgerRouter({
      transactions: [normal, refund, transferTransaction(402)],
      budgets: [{
        id: 600,
        month: '2026-08',
        scope: 'PERSONAL',
        ownerMemberId: 100,
        categoryId: 300,
        amount: 20_000,
        version: 0,
      }],
    })
    render(<App />)
    const categorySection = (await screen.findByRole('heading', { name: 'Category 예산' }))
      .closest('section') as HTMLElement
    const categoryRow = within(categorySection).getByText('식비').closest('li') as HTMLElement

    fireEvent.click(within(categoryRow).getByRole('button', { name: '사용 내역' }))

    const dialog = await screen.findByRole('dialog', { name: 'Owner · 식비' })
    expect(within(dialog).getByText('식비 환불')).toBeInTheDocument()
    expect(within(dialog).getByText('+2,000원')).toBeInTheDocument()
    expect(within(dialog).queryByText('계좌 이체')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('from=2026-08-01')
        && url.includes('to=2026-08-31')
        && url.includes('type=EXPENSE')
        && url.includes('scope=PERSONAL')
        && url.includes('ownerMemberId=100')
        && url.includes('categoryId=300')
    })).toBe(true)
  })

  it('focuses the Budget drill-down and restores its opener after Escape', async () => {
    useBudgetUrl()
    installLedgerRouter()
    render(<App />)
    const opener = await screen.findByRole('button', { name: '우리 전체 사용 내역 보기' })

    fireEvent.click(opener)

    const dialog = await screen.findByRole('dialog', { name: '우리 전체' })
    const closeButton = within(dialog).getByRole('button', { name: '예산 사용 내역 닫기' })
    await waitFor(() => expect(closeButton).toHaveFocus())
    fireEvent.keyDown(window, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog', { name: '우리 전체' }))
      .not.toBeInTheDocument())
    await waitFor(() => expect(opener).toHaveFocus())
  })

  it('activates Statistics and renders backend summary, comparison, trend, and breakdowns', async () => {
    useStatisticsUrl()
    const { fetchMock } = installLedgerRouter()
    render(<App />)

    expect(await screen.findByRole('heading', { name: '이번 기간 요약' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '통계' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: /자산/ })).toBeDisabled()
    expect(screen.getAllByText('3,000,000원').length).toBeGreaterThan(0)
    expect(screen.getAllByText('128,450원').length).toBeGreaterThan(0)
    expect(screen.getAllByText('33.3%').length).toBeGreaterThan(0)
    expect(screen.getByText('200,000원 증가 · 7.1% 증가')).toBeInTheDocument()
    expect(screen.getByText('21,550원 감소 · 14.4% 감소')).toBeInTheDocument()
    expect(screen.getByText('2026-08')).toBeInTheDocument()
    expect(screen.getByText('지난 취미')).toBeInTheDocument()
    expect(screen.getByText('보관됨')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/statistics?')
        && url.includes('from=2026-08-01')
        && url.includes('to=2026-08-31')
        && url.includes('compareFrom=2026-07-01')
        && url.includes('compareTo=2026-07-31')
        && !url.includes('scope=')
    })).toBe(true)
  })

  it('maps Statistics member scope and hides stale all-scope numbers while pending', async () => {
    useStatisticsUrl()
    const options: RouterOptions = {}
    const { fetchMock } = installLedgerRouter(options)
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('3,000,000원').length).toBeGreaterThan(0))

    let releaseStatistics!: () => void
    options.statisticsGate = new Promise<void>((resolve) => {
      releaseStatistics = resolve
    })
    const scope = screen.getByRole('navigation', { name: '통계 보기 범위' })
    fireEvent.click(within(scope).getByRole('button', { name: 'Member' }))

    expect(screen.getByRole('status')).toHaveTextContent('선택한 조건의 통계를 계산하고 있어요.')
    expect(screen.queryAllByText('3,000,000원')).toHaveLength(0)
    expect(window.location.search)
      .toBe('?screen=statistics&preset=this-month&view=member&memberId=101')
    releaseStatistics()

    expect(await screen.findByText('저축·저축률은 전체 보기에서 제공해요.'))
      .toBeInTheDocument()
    expect(screen.getAllByText('전체 보기 전용')).toHaveLength(2)
    expect(screen.queryAllByText('1,000,000원')).toHaveLength(0)
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/statistics?')
        && url.includes('scope=PERSONAL')
        && url.includes('ownerMemberId=101')
    })).toBe(true)
  })

  it('keeps custom Statistics periods in canonical URL and restores popstate scope', async () => {
    useStatisticsUrl('preset=custom&from=2026-02-30&to=2026-01-01&view=member&memberId=999')
    installLedgerRouter()
    render(<App />)
    await screen.findByRole('heading', { name: '이번 기간 요약' })
    expect(window.location.search).toBe('?screen=statistics&preset=this-month&view=all')

    fireEvent.change(screen.getByLabelText('통계 기간'), { target: { value: 'custom' } })
    fireEvent.change(screen.getByLabelText('시작일'), { target: { value: '2026-06-15' } })
    fireEvent.change(screen.getByLabelText('종료일'), { target: { value: '2026-08-20' } })
    fireEvent.click(screen.getByRole('button', { name: '기간 적용' }))
    expect(window.location.search)
      .toBe('?screen=statistics&preset=custom&view=all&from=2026-06-15&to=2026-08-20')

    window.history.pushState(
      {},
      '',
      '/?screen=statistics&preset=recent-3-months&view=shared',
    )
    fireEvent(window, new PopStateEvent('popstate'))

    await waitFor(() => expect(screen.getByLabelText('통계 기간'))
      .toHaveValue('recent-3-months'))
    expect(within(screen.getByRole('navigation', { name: '통계 보기 범위' }))
      .getByRole('button', { name: '공동' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('loads every filtered transaction and savings drill-down with refund semantics', async () => {
    useStatisticsUrl()
    const normal = primaryTransaction({ id: 400, amount: 12_000 })
    const refund = {
      ...primaryTransaction({ id: 401, amount: 2_000, memo: '부분 환불' }),
      adjustmentType: 'REFUND',
    }
    const { fetchMock } = installLedgerRouter({ transactions: [normal, refund] })
    render(<App />)
    const categorySection = (await screen.findByRole('heading', { name: '어디에 썼나요' }))
      .closest('section') as HTMLElement
    const categoryOpener = within(categorySection).getByRole('button', { name: /식비/ })

    fireEvent.click(categoryOpener)

    const categoryDialog = await screen.findByRole('dialog', { name: '식비 소비·환불' })
    expect(within(categoryDialog).getByText('식비 환불')).toBeInTheDocument()
    expect(within(categoryDialog).getByText('+2,000원')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('type=EXPENSE')
        && url.includes('categoryId=300')
        && url.includes('from=2026-08-01')
        && url.includes('to=2026-08-31')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(categoryOpener).toHaveFocus())

    const summarySection = screen.getByRole('heading', { name: '이번 기간 요약' })
      .closest('section') as HTMLElement
    const incomeOpener = within(summarySection).getByRole('button', { name: /^수입/ })
    fireEvent.click(incomeOpener)
    await screen.findByRole('dialog', { name: '수입 원장' })
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('type=INCOME')
        && !url.includes('categoryId=')
        && !url.includes('accountId=')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(incomeOpener).toHaveFocus())

    const spendingOpener = within(summarySection).getByRole('button', { name: /^순소비/ })
    fireEvent.click(spendingOpener)
    await screen.findByRole('dialog', { name: '소비·환불 원장' })
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('type=EXPENSE')
        && !url.includes('categoryId=')
        && !url.includes('accountId=')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(spendingOpener).toHaveFocus())

    const accountSection = screen.getByRole('heading', { name: '어떤 Account로 썼나요' })
      .closest('section') as HTMLElement
    const accountOpener = within(accountSection).getByRole('button', { name: /주거래 통장/ })
    fireEvent.click(accountOpener)
    await screen.findByRole('dialog', { name: '주거래 통장 소비·환불' })
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('type=EXPENSE')
        && url.includes('accountId=200')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(accountOpener).toHaveFocus())

    const subjectSection = screen.getByRole('heading', { name: '누가 썼나요' })
      .closest('section') as HTMLElement
    const memberOpener = within(subjectSection).getByRole('button', { name: /Member/ })
    fireEvent.click(memberOpener)
    await screen.findByRole('dialog', { name: 'Member 소비·환불' })
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('scope=PERSONAL')
        && url.includes('ownerMemberId=101')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(memberOpener).toHaveFocus())

    const sharedOpener = within(subjectSection).getByRole('button', { name: /공동/ })
    fireEvent.click(sharedOpener)
    await screen.findByRole('dialog', { name: '공동 소비·환불' })
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = String(input)
      return url.includes('/api/v1/transactions?')
        && url.includes('scope=SHARED')
        && !url.includes('ownerMemberId=')
    })).toBe(true)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(sharedOpener).toHaveFocus())

    const savingsOpener = within(summarySection).getByRole('button', { name: /저축.*원장 보기/ })
    fireEvent.click(savingsOpener)
    const savingsDialog = await screen.findByRole('dialog', { name: '저축 활동' })
    expect(within(savingsDialog).getByText('주거래 통장 → 비상금 통장')).toBeInTheDocument()
    expect(within(savingsDialog).getByText('+1,000,000원')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) =>
      String(input).includes('/api/v1/statistics/savings-activities?from=2026-08-01&to=2026-08-31')))
      .toBe(true)
  })

  it('shows generated provenance as text in Calendar and Statistics drill-downs', async () => {
    const generated = {
      ...primaryTransaction({ id: 410, amount: 12_000 }),
      generatedFromRecurringId: 800,
      recurrenceDate: '2026-08-27',
    }
    useCalendarUrl()
    installLedgerRouter({ transactions: [generated] })
    const { unmount } = render(<App />)
    const selectedDay = (await screen.findByRole('heading', { name: '8월 27일의 기록' }))
      .closest('section') as HTMLElement
    expect(await within(selectedDay).findByText('반복')).toBeInTheDocument()
    unmount()

    useStatisticsUrl()
    installLedgerRouter({
      transactions: [generated],
      savingsActivities: [{
        ...savingsActivities[0],
        generatedFromRecurringId: 801,
        recurrenceDate: '2026-08-10',
      }],
    })
    render(<App />)
    const categorySection = (await screen.findByRole('heading', { name: '어디에 썼나요' }))
      .closest('section') as HTMLElement
    fireEvent.click(within(categorySection).getByRole('button', { name: /식비/ }))
    const categoryDialog = await screen.findByRole('dialog', { name: '식비 소비·환불' })
    expect(await within(categoryDialog).findByText('반복')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })

    const summarySection = screen.getByRole('heading', { name: '이번 기간 요약' })
      .closest('section') as HTMLElement
    fireEvent.click(within(summarySection).getByRole('button', { name: /저축.*원장 보기/ }))
    const savingsDialog = await screen.findByRole('dialog', { name: '저축 활동' })
    expect(await within(savingsDialog).findByText('반복')).toBeInTheDocument()
  })

  it('renders unavailable percentages and keeps amount and percent directions independent', async () => {
    useStatisticsUrl()
    installLedgerRouter({
      statistics: {
        ...statisticsData,
        summary: {
          ...statisticsData.summary,
          incomeAmount: 0,
          savingsAmount: -10_000,
          savingsRate: null,
        },
        comparison: {
          ...statisticsData.comparison,
          incomeDifferenceAmount: 100_000,
          incomePercentChange: null,
          netSpendingDifferenceAmount: 50_000,
          netSpendingPercentChange: -50,
          savingsRateDifferencePoints: null,
        },
        months: [{
          ...statisticsData.months[0],
          incomeAmount: 0,
          savingsAmount: -10_000,
          savingsRate: null,
        }],
      },
    })
    render(<App />)

    expect(await screen.findByText('100,000원 증가 · 비율 계산 불가')).toBeInTheDocument()
    expect(screen.getByText('50,000원 증가 · 50% 감소')).toBeInTheDocument()
    expect(screen.getByText('비교 계산 불가')).toBeInTheDocument()
    expect(screen.getAllByText('계산 불가').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('-10,000원').length).toBeGreaterThanOrEqual(2)
  })

  it('uses Household today for Statistics Paw and preserves Calendar, Budget, and disabled Assets', async () => {
    useStatisticsUrl()
    installLedgerRouter()
    render(<App />)
    await screen.findByRole('heading', { name: '통계' })

    const quickEntry = screen.getByRole('button', { name: '2026-08-28 빠른 입력 열기' })
    fireEvent.click(quickEntry)
    const dialog = await screen.findByRole('dialog', { name: '빠른 입력' })
    expect(within(dialog).getByLabelText('날짜')).toHaveValue('2026-08-28')
    fireEvent.click(within(dialog).getByRole('button', { name: '빠른 입력 닫기' }))

    fireEvent.click(screen.getByRole('button', { name: 'Calendar' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Calendar' }))
      .toHaveAttribute('aria-current', 'page'))
    fireEvent.click(screen.getByRole('button', { name: '예산' }))
    expect(await screen.findByRole('heading', { name: '예산' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /자산/ })).toBeDisabled()
  })
})
