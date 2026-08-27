import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
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
}

const currentHousehold = {
  householdId: 10,
  name: '테스트 Household',
  baseCurrency: 'KRW',
  timezone: 'Asia/Seoul',
  members: [
    { memberId: 101, userId: 2, displayName: 'Member', role: 'MEMBER' },
    { memberId: 100, userId: 1, displayName: 'Owner', role: 'OWNER' },
  ],
}

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

const creditCardAccount = {
  ...checkingAccount,
  id: 202,
  name: '생활 카드',
  type: 'CREDIT_CARD',
  nature: 'LIABILITY',
  openingBalance: 0,
  currentBalance: 0,
  sortOrder: 2,
}

const incomeCategory = {
  ...expenseCategory,
  id: 301,
  name: '급여',
  type: 'INCOME',
}

const expenseTransaction = {
  id: 400,
  type: 'EXPENSE',
  amount: 12000,
  scope: 'PERSONAL',
  owner: { memberId: 100, userId: 1, displayName: 'Owner' },
  payer: { memberId: 100, userId: 1, displayName: 'Owner' },
  category: { id: 300, name: '식비', type: 'EXPENSE', archived: false },
  occurredAt: '2026-08-27T03:00:00Z',
  memo: '점심',
  adjustmentType: 'NORMAL',
  version: 0,
  entries: [{
    id: 500,
    role: 'PRIMARY',
    balanceDelta: -12000,
    account: {
      id: 200,
      name: '주거래 통장',
      type: 'CHECKING',
      nature: 'ASSET',
      archived: false,
    },
  }],
}

type RouterOptions = {
  accounts?: Array<Record<string, unknown>>
  groups?: Array<Record<string, unknown>>
  categories?: Array<Record<string, unknown>>
  transactions?: Array<Record<string, unknown>>
  failTransactionCreate?: boolean
}

function installLedgerRouter(options: RouterOptions = {}) {
  const state = {
    accounts: [...(options.accounts ?? [])],
    groups: [...(options.groups ?? [])],
    categories: [...(options.categories ?? [])],
    transactions: [...(options.transactions ?? [])],
  }

  function transactionResponse(
    inputBody: Record<string, unknown>,
    id: number,
    version: number,
  ) {
    const amount = Number(inputBody.amount)
    const type = String(inputBody.type)
    const category = state.categories.find(
      (item) => Number(item.id) === Number(inputBody.categoryId),
    )
    const account = state.accounts.find(
      (item) => Number(item.id) === Number(inputBody.accountId),
    )
    const source = state.accounts.find(
      (item) => Number(item.id) === Number(inputBody.sourceAccountId),
    )
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
    const memberReference = (memberId: unknown) => {
      const member = currentHousehold.members.find(
        (item) => item.memberId === Number(memberId),
      )
      return member
        ? { memberId: member.memberId, userId: member.userId, displayName: member.displayName }
        : null
    }
    const entries = type === 'TRANSFER'
      ? [
          {
            id: 501,
            role: 'SOURCE',
            balanceDelta: -amount,
            account: accountReference(source),
          },
          {
            id: 502,
            role: 'DESTINATION',
            balanceDelta: destination?.nature === 'ASSET' ? amount : -amount,
            account: accountReference(destination),
          },
        ]
      : [{
          id: 501,
          role: 'PRIMARY',
          balanceDelta: type === 'INCOME' || account?.type === 'CREDIT_CARD' ? amount : -amount,
          account: accountReference(account),
        }]
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
      entries,
    }
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url === '/api/v1/me') return jsonResponse(currentUser)
    if (url === '/api/v1/households/current') return jsonResponse(currentHousehold)

    if (url === '/api/v1/accounts' && method === 'GET') return jsonResponse(state.accounts)
    if (url === '/api/v1/accounts' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = {
        ...checkingAccount,
        ...inputBody,
        id: 201,
        currentBalance: inputBody.openingBalance,
        owner: { memberId: 100, userId: 1, displayName: 'Owner' },
        archived: false,
      }
      state.accounts.push(created)
      return jsonResponse(created, 201)
    }
    if (url.startsWith('/api/v1/accounts/') && method === 'PATCH') {
      return jsonResponse({ ...state.accounts[0], archived: true })
    }

    if (url === '/api/v1/category-groups' && method === 'GET') return jsonResponse(state.groups)
    if (url === '/api/v1/category-groups' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = { id: 250, ...inputBody, archived: false }
      state.groups.push(created)
      return jsonResponse(created, 201)
    }
    if (url.startsWith('/api/v1/category-groups/') && method === 'PATCH') {
      return jsonResponse({ ...state.groups[0], archived: true })
    }

    if (url === '/api/v1/categories' && method === 'GET') return jsonResponse(state.categories)
    if (url === '/api/v1/categories' && method === 'POST') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = { id: 302, group: null, ...inputBody, archived: false }
      state.categories.push(created)
      return jsonResponse(created, 201)
    }
    if (url.startsWith('/api/v1/categories/') && method === 'PATCH') {
      return jsonResponse({ ...state.categories[0], archived: true })
    }

    if (url === '/api/v1/transactions' && method === 'GET') {
      return jsonResponse(state.transactions)
    }
    if (url === '/api/v1/transactions' && method === 'POST') {
      if (options.failTransactionCreate) {
        return jsonResponse({ code: 'CATEGORY_TYPE_MISMATCH', message: '분류를 확인해 주세요.' }, 422)
      }
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const created = transactionResponse(inputBody, 401 + state.transactions.length, 0)
      state.transactions.unshift(created)
      return jsonResponse(created, 201)
    }
    if (/^\/api\/v1\/transactions\/\d+$/.test(url) && method === 'PATCH') {
      const inputBody = JSON.parse(String(init?.body)) as Record<string, unknown>
      const current = state.transactions[0]
      const updated = transactionResponse(
        inputBody,
        Number(current.id),
        Number(current.version) + 1,
      )
      state.transactions[0] = updated
      return jsonResponse(updated)
    }
    if (url.startsWith('/api/v1/transactions/') && method === 'DELETE') {
      state.transactions = []
      return jsonResponse(null, 204)
    }

    return jsonResponse({ code: 'NOT_MOCKED', message: url }, 500)
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, state }
}

describe('App', () => {
  it('renders the loading state while the current user request is pending', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))

    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent(
      '현재 사용자와 Household를 확인하고 있습니다.',
    )
  })

  it('renders the current household and empty ledger on success', async () => {
    installLedgerRouter()

    render(<App />)

    expect(await screen.findByRole('heading', { level: 2, name: 'Owner' })).toBeInTheDocument()
    expect(screen.getByText('owner@example.test')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '빠른 입력' })).toBeInTheDocument()
    expect(screen.getByText(/아직 거래가 없습니다/)).toBeInTheDocument()
  })

  it('renders an authentication message on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 401)))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('인증이 필요합니다.')
    expect(screen.getByText(/Cloudflare Access 인증/)).toBeInTheDocument()
  })

  it('renders an unregistered user message on 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ code: 'USER_NOT_REGISTERED' }, 403)),
    )

    render(<App />)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('등록된 사용자가 아닙니다.'),
    )
    expect(screen.getByText(/내부 User와 Household membership/)).toBeInTheDocument()
  })

  it('creates an account and category group without leaving the setup screen', async () => {
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    await screen.findByRole('heading', { name: '계좌 설정' })

    fireEvent.change(screen.getByLabelText('계좌 이름'), { target: { value: '생활비 통장' } })
    fireEvent.click(screen.getByRole('button', { name: '계좌 추가' }))
    expect((await screen.findAllByText('생활비 통장')).length).toBeGreaterThan(0)
    const accountCreateCall = fetchMock.mock.calls.find(
      ([input, init]) => input === '/api/v1/accounts' && init?.method === 'POST',
    )
    expect(JSON.parse(String(accountCreateCall?.[1]?.body))).toEqual(
      expect.objectContaining({ ownerMemberId: 100 }),
    )

    fireEvent.change(screen.getByLabelText('Group 이름'), { target: { value: '생활' } })
    fireEvent.click(screen.getByRole('button', { name: 'Group 추가' }))
    expect((await screen.findAllByText('생활')).length).toBeGreaterThan(0)
  })

  it('forces liability and the current member when a credit card account is created', async () => {
    const { fetchMock } = installLedgerRouter()
    render(<App />)
    const heading = await screen.findByRole('heading', { name: '계좌 설정' })
    const panel = heading.closest('section') as HTMLElement

    fireEvent.change(within(panel).getByLabelText('계좌 이름'), { target: { value: '생활 카드' } })
    fireEvent.change(within(panel).getByLabelText('유형'), { target: { value: 'CREDIT_CARD' } })
    expect(within(panel).getByText(/신용카드는 LIABILITY/)).toBeInTheDocument()
    fireEvent.click(within(panel).getByRole('button', { name: '계좌 추가' }))

    await within(panel).findByText('생활 카드')
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) => input === '/api/v1/accounts' && init?.method === 'POST',
    )
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual(expect.objectContaining({
      type: 'CREDIT_CARD',
      nature: 'LIABILITY',
      ownerMemberId: 100,
      savingsEnabled: false,
    }))
  })

  it('creates and renders a transaction through the quick entry flow', async () => {
    const { fetchMock } = installLedgerRouter({
      accounts: [checkingAccount],
      categories: [expenseCategory, incomeCategory],
    })
    render(<App />)
    await screen.findByRole('heading', { name: '빠른 입력' })

    fireEvent.change(screen.getByLabelText(/금액/), { target: { value: '12000' } })
    fireEvent.change(screen.getByLabelText('날짜'), { target: { value: '2026-08-27' } })
    fireEvent.change(screen.getByLabelText('메모 (선택)'), { target: { value: '점심' } })
    fireEvent.click(screen.getByRole('button', { name: '거래 저장' }))

    expect(await screen.findByText('점심')).toBeInTheDocument()
    expect(screen.getByText('−12,000원')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/transactions',
      expect.objectContaining({ method: 'POST' }),
    )
    const createCall = fetchMock.mock.calls.find(
      ([input, init]) => input === '/api/v1/transactions' && init?.method === 'POST',
    )
    const requestBody = JSON.parse(String(createCall?.[1]?.body)) as Record<string, unknown>
    expect(requestBody.occurredAt).toBe('2026-08-27T03:00:00.000Z')
    expect(requestBody).toEqual(expect.objectContaining({
      ownerMemberId: 100,
      payerMemberId: 100,
      sourceAccountId: null,
      destinationAccountId: null,
    }))
  })

  it('creates transfers and card expenses with role-based account entries', async () => {
    const { fetchMock } = installLedgerRouter({
      accounts: [checkingAccount, savingsAccount, creditCardAccount],
      categories: [expenseCategory, incomeCategory],
    })
    render(<App />)
    await screen.findByRole('heading', { name: '빠른 입력' })

    fireEvent.click(screen.getByRole('button', { name: '이체' }))
    expect(screen.queryByLabelText('범위')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Category')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/금액/), { target: { value: '8000' } })
    fireEvent.change(screen.getByLabelText('출금 Account'), { target: { value: '200' } })
    fireEvent.change(screen.getByLabelText('입금 Account'), { target: { value: '201' } })
    fireEvent.click(screen.getByRole('button', { name: '거래 저장' }))

    const recent = await screen.findByRole('heading', { name: '최근 거래' })
    const recentPanel = recent.closest('section') as HTMLElement
    expect(await within(recentPanel).findByText(/주거래 통장 → 비상금 통장/)).toBeInTheDocument()
    expect(within(recentPanel).getByText('↔ 8,000원')).toBeInTheDocument()
    const transferCreateCall = fetchMock.mock.calls.filter(
      ([input, init]) => input === '/api/v1/transactions' && init?.method === 'POST',
    )[0]
    expect(JSON.parse(String(transferCreateCall?.[1]?.body))).toEqual(expect.objectContaining({
      type: 'TRANSFER',
      scope: null,
      ownerMemberId: null,
      payerMemberId: null,
      categoryId: null,
      accountId: null,
      sourceAccountId: 200,
      destinationAccountId: 201,
    }))

    fireEvent.change(screen.getByLabelText(/금액/), { target: { value: '12000' } })
    fireEvent.change(screen.getByLabelText('Account'), { target: { value: '202' } })
    fireEvent.click(screen.getByRole('button', { name: '거래 저장' }))

    expect(await within(recentPanel).findByText(/생활 카드/)).toBeInTheDocument()
    const transactionCreateCalls = fetchMock.mock.calls.filter(
      ([input, init]) => input === '/api/v1/transactions' && init?.method === 'POST',
    )
    expect(JSON.parse(String(transactionCreateCalls[1]?.[1]?.body))).toEqual(
      expect.objectContaining({
        type: 'EXPENSE',
        accountId: 202,
        sourceAccountId: null,
        destinationAccountId: null,
      }),
    )
  })

  it('preserves transaction input when server validation fails', async () => {
    installLedgerRouter({
      accounts: [checkingAccount],
      categories: [expenseCategory],
      failTransactionCreate: true,
    })
    render(<App />)
    await screen.findByRole('heading', { name: '빠른 입력' })

    const amount = screen.getByLabelText(/금액/)
    const memo = screen.getByLabelText('메모 (선택)')
    fireEvent.change(amount, { target: { value: '15000' } })
    fireEvent.change(memo, { target: { value: '입력 유지' } })
    fireEvent.click(screen.getByRole('button', { name: '거래 저장' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('분류를 확인해 주세요.')
    expect(amount).toHaveValue(15000)
    expect(memo).toHaveValue('입력 유지')
  })

  it('edits and deletes a recent transaction', async () => {
    const { fetchMock } = installLedgerRouter({
      accounts: [checkingAccount],
      categories: [expenseCategory, incomeCategory],
      transactions: [expenseTransaction],
    })
    render(<App />)
    const recent = await screen.findByRole('heading', { name: '최근 거래' })
    const panel = recent.closest('section') as HTMLElement

    fireEvent.click(within(panel).getByRole('button', { name: '상세' }))
    expect(within(panel).getByText(/PRIMARY/)).toBeInTheDocument()

    fireEvent.click(within(panel).getByRole('button', { name: '수정' }))
    expect(await screen.findByRole('heading', { name: '거래 수정' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/금액/), { target: { value: '20000' } })
    fireEvent.click(screen.getByRole('button', { name: '수정 저장' }))

    await waitFor(() => expect(screen.getByText('−20,000원')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/transactions/400',
      expect.objectContaining({ method: 'PATCH' }),
    )

    fireEvent.click(within(panel).getByRole('button', { name: '삭제' }))
    expect(await screen.findByText(/아직 거래가 없습니다/)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/transactions/400?version=1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
