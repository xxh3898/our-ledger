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

type RouterOptions = {
  accounts?: Array<Record<string, unknown>>
  groups?: Array<Record<string, unknown>>
  categories?: Array<Record<string, unknown>>
  transactions?: Array<Record<string, unknown>>
  failTransactionCreate?: boolean
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
  }

  function matchesFilter(transaction: Record<string, unknown>, url: URL) {
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

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = typeof input === 'string' ? input : input.toString()
    const url = new URL(path, 'http://ledger.test')
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.pathname === '/api/v1/me') return jsonResponse(currentUser)
    if (url.pathname === '/api/v1/households/current') return jsonResponse(currentHousehold)

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

    if (url.pathname === '/api/v1/calendar/month' && method === 'GET') {
      return jsonResponse(calendarResponse(url))
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
    expect(screen.getByRole('heading', { name: '둘의 다음 목표를 담을 자리' }))
      .toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Calendar 보기 범위' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '2026년 8월' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '8월 27일의 기록' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '주요 메뉴' })).toBeInTheDocument()
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

  it('renders unimplemented bottom tabs as disabled instead of fake pages', async () => {
    useCalendarUrl()
    installLedgerRouter()
    render(<App />)
    const navigation = await screen.findByRole('navigation', { name: '주요 메뉴' })

    expect(within(navigation).getByRole('button', { name: /Calendar/ }))
      .toHaveAttribute('aria-current', 'page')
    expect(within(navigation).getByRole('button', { name: /예산/ })).toBeDisabled()
    expect(within(navigation).getByRole('button', { name: /통계/ })).toBeDisabled()
    expect(within(navigation).getByRole('button', { name: /자산/ })).toBeDisabled()
  })
})
