import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { BudgetScreen } from './BudgetScreen.tsx'
import { GoalAccountLinkSheet } from './GoalAccountLinkSheet.tsx'
import { MarriageGoalCard, type GoalViewState } from './MarriageGoalCard.tsx'
import { MarriageGoalScreen } from './MarriageGoalScreen.tsx'
import { MarriageGoalSheet } from './MarriageGoalSheet.tsx'
import { QuickEntrySheet } from './QuickEntrySheet.tsx'
import { RefundSheet } from './RefundSheet.tsx'
import { SettingsSheet } from './SettingsSheet.tsx'
import { StatisticsScreen } from './StatisticsScreen.tsx'
import {
  currentBudgetMonth,
  isBudgetScreen,
  moveBudgetMonth,
  normalizeBudgetMonth,
  serializeBudgetState,
} from './budgetState.ts'
import {
  type CalendarNavigationState,
  calendarDates,
  calendarFilter,
  moveCalendarMonth,
  normalizeCalendarState,
  serializeCalendarState,
} from './calendarState.ts'
import { todayInTimeZone } from './dateTime.ts'
import {
  type CalendarMonth,
  type CurrentHousehold,
  type CurrentUser,
  type LedgerTransaction,
  type MarriageGoalView,
  type RefundSummary,
  LedgerApiError,
  deleteTransaction,
  loadCalendarMonth,
  loadCurrentUser,
  loadDayTransactions,
  loadReferenceData,
  loadRefundSummary,
  loadMarriageGoal,
  unlinkMarriageGoalAccount,
} from './ledgerApi.ts'
import { entryByRole } from './transactionUtils.ts'
import {
  isStatisticsScreen,
  normalizeStatisticsState,
  serializeStatisticsState,
  type StatisticsNavigationState,
} from './statisticsState.ts'

type WorkspaceScreen = 'calendar' | 'budget' | 'statistics' | 'goal'

function screenFromSearch(search: string): WorkspaceScreen {
  if (new URLSearchParams(search).get('screen') === 'goal') return 'goal'
  if (isStatisticsScreen(search)) return 'statistics'
  if (isBudgetScreen(search)) return 'budget'
  return 'calendar'
}

type ViewState =
  | { status: 'loading' }
  | { status: 'ready'; user: CurrentUser }
  | { status: 'authentication-required' }
  | { status: 'access-denied'; code?: string }
  | { status: 'error' }

type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string }

type ReferenceData = Awaited<ReturnType<typeof loadReferenceData>>

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '요청을 처리하지 못했습니다.'
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

function AccessState({ state }: { state: ViewState }) {
  if (state.status === 'loading') {
    return (
      <main className="access-state" role="status">
        <span className="loading-paw" aria-hidden="true">🐾</span>
        <strong>우리의 장부를 열고 있어요.</strong>
        <span>현재 사용자와 Household를 확인합니다.</span>
      </main>
    )
  }

  if (state.status === 'authentication-required') {
    return (
      <main className="access-state access-state--error" role="alert">
        <strong>인증이 필요합니다.</strong>
        <span>Cloudflare Access 인증 후 다시 열어 주세요.</span>
      </main>
    )
  }

  if (state.status === 'access-denied') {
    const isUnregistered = state.code === 'USER_NOT_REGISTERED'
    const isDisabled = state.code === 'USER_DISABLED'
    return (
      <main className="access-state access-state--error" role="alert">
        <strong>
          {isUnregistered
            ? '등록된 사용자가 아닙니다.'
            : isDisabled
              ? '비활성화된 사용자입니다.'
              : 'Household 접근 권한이 없습니다.'}
        </strong>
        <span>내부 User와 Household membership을 확인해 주세요.</span>
      </main>
    )
  }

  return (
    <main className="access-state access-state--error" role="alert">
      <strong>현재 정보를 불러오지 못했습니다.</strong>
      <span>잠시 뒤 다시 시도해 주세요.</span>
    </main>
  )
}

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function differenceCopy(summary: CalendarMonth['summary']) {
  if (summary.differenceAmount === 0) return '지난달과 같아요.'
  const amount = formatWon(Math.abs(summary.differenceAmount))
  return summary.differenceAmount > 0
    ? `지난달보다 ${amount} 더 썼어요.`
    : `지난달보다 ${amount} 덜 썼어요.`
}

function viewLabel(navigation: CalendarNavigationState, household: CurrentHousehold) {
  if (navigation.view === 'shared') return '공동'
  if (navigation.view === 'member') {
    return household.members.find((member) => member.memberId === navigation.memberId)
      ?.displayName ?? '개인'
  }
  return '우리 전체'
}

function CoupleHeader({
  user,
  household,
  onOpenSettings,
}: {
  user: CurrentUser
  household: CurrentHousehold
  onOpenSettings: () => void
}) {
  return (
    <header className="couple-header">
      <div>
        <p className="brand-kicker">둘이 쓰는 하나의 생활 기록</p>
        <h1>우리의 장부</h1>
        <p className="household-meta">
          {household.name} · {user.email} · {user.role}
        </p>
      </div>
      <div className="couple-actions">
        <ul className="member-avatars" aria-label="Household 구성원">
          {household.members.map((member) => (
            <li key={member.memberId}>
              <span className="avatar-placeholder" aria-hidden="true">
                {member.displayName.slice(0, 1)}
              </span>
              <span>
                {member.displayName}
                {member.userId === user.userId && <small>나</small>}
              </span>
            </li>
          ))}
        </ul>
        <button className="settings-button" type="button" onClick={onOpenSettings}>
          설정
        </button>
      </div>
    </header>
  )
}

function SpendingHero({
  navigation,
  household,
  state,
  onRetry,
}: {
  navigation: CalendarNavigationState
  household: CurrentHousehold
  state: AsyncState<CalendarMonth>
  onRetry: () => void
}) {
  const monthNumber = Number(navigation.month.slice(5))
  return (
    <section
      className="spending-hero"
      aria-labelledby="spending-title"
      aria-busy={state.status === 'loading'}
    >
      <p className="section-kicker">{viewLabel(navigation, household)} · {monthNumber}월</p>
      <h2 id="spending-title">이번 달 우리가 쓴 돈</h2>
      {state.status === 'loading' && (
        <div className="summary-skeleton" role="status">월 소비를 계산하고 있어요.</div>
      )}
      {state.status === 'error' && (
        <div className="inline-error" role="alert">
          <span>{state.message}</span>
          <button type="button" onClick={onRetry}>다시 불러오기</button>
        </div>
      )}
      {state.status === 'ready' && (
        <>
          <strong className="hero-amount">
            {formatWon(state.data.summary.netSpendingAmount)}
          </strong>
          <p className="difference-copy">{differenceCopy(state.data.summary)}</p>
        </>
      )}
    </section>
  )
}

function ScopeSelector({
  user,
  household,
  navigation,
  onChange,
}: {
  user: CurrentUser
  household: CurrentHousehold
  navigation: CalendarNavigationState
  onChange: (state: CalendarNavigationState) => void
}) {
  return (
    <nav className="scope-selector" aria-label="Calendar 보기 범위">
      <button
        type="button"
        aria-pressed={navigation.view === 'all'}
        onClick={() => onChange({ ...navigation, view: 'all', memberId: null })}
      >
        전체
      </button>
      {household.members.map((member) => (
        <button
          key={member.memberId}
          type="button"
          aria-pressed={navigation.view === 'member' && navigation.memberId === member.memberId}
          onClick={() => onChange({
            ...navigation,
            view: 'member',
            memberId: member.memberId,
          })}
        >
          {member.displayName}{member.userId === user.userId ? ' · 나' : ''}
        </button>
      ))}
      <button
        type="button"
        aria-pressed={navigation.view === 'shared'}
        onClick={() => onChange({ ...navigation, view: 'shared', memberId: null })}
      >
        공동
      </button>
    </nav>
  )
}

function MonthNavigation({
  month,
  onMove,
}: {
  month: string
  onMove: (offset: number) => void
}) {
  const [year, monthNumber] = month.split('-').map(Number)
  return (
    <div className="month-navigation">
      <button type="button" aria-label="이전 달" onClick={() => onMove(-1)}>‹</button>
      <h2>{year}년 {monthNumber}월</h2>
      <button type="button" aria-label="다음 달" onClick={() => onMove(1)}>›</button>
    </div>
  )
}

function CalendarGrid({
  household,
  navigation,
  state,
  onSelect,
}: {
  household: CurrentHousehold
  navigation: CalendarNavigationState
  state: AsyncState<CalendarMonth>
  onSelect: (date: string) => void
}) {
  const today = todayInTimeZone(household.timezone)
  const dayMap = new Map(
    state.status === 'ready' ? state.data.days.map((day) => [day.date, day]) : [],
  )
  const dates = calendarDates(navigation.month)

  return (
    <section className="calendar-card" aria-label={`${navigation.month} Calendar`}>
      <div className="weekday-row" aria-hidden="true">
        {['일', '월', '화', '수', '목', '금', '토'].map((weekday) => (
          <span key={weekday}>{weekday}</span>
        ))}
      </div>
      <div className="calendar-grid" aria-busy={state.status === 'loading'}>
        {dates.map((date, index) => {
          if (!date) return <span className="calendar-empty" key={`empty-${index}`} />
          const day = dayMap.get(date)
          const isFuture = date > today
          const noSpend = state.status === 'ready'
            && !isFuture
            && (day?.netSpendingAmount ?? 0) === 0
          const selected = navigation.date === date
          const dayStatus = state.status === 'loading'
            ? '날짜 정보 불러오는 중'
            : state.status === 'error'
              ? '날짜 정보 확인 실패'
              : day
                ? `거래 ${day.transactionCount}건`
                : '거래 없음'
          const label = [
            `${Number(date.slice(-2))}일`,
            date === today ? '오늘' : null,
            dayStatus,
            noSpend ? '무지출' : null,
          ].filter(Boolean).join(', ')
          return (
            <button
              key={date}
              type="button"
              className={[
                'calendar-day',
                selected ? 'is-selected' : '',
                date === today ? 'is-today' : '',
                isFuture ? 'is-future' : '',
              ].filter(Boolean).join(' ')}
              aria-label={label}
              aria-pressed={selected}
              aria-current={date === today ? 'date' : undefined}
              onClick={() => onSelect(date)}
            >
              <time dateTime={date}>{Number(date.slice(-2))}</time>
              <span className="day-markers">
                {day && day.transactionCount > 0 && (
                  <span className="transaction-count">{day.transactionCount}</span>
                )}
                {noSpend && <span className="no-spend-paw" aria-label="무지출">🐾</span>}
              </span>
              {day && day.netSpendingAmount !== 0 && (
                <small>{day.netSpendingAmount.toLocaleString('ko-KR')}</small>
              )}
            </button>
          )
        })}
      </div>
      {state.status === 'loading' && (
        <p className="calendar-status" role="status">새 범위의 달력을 불러오고 있어요.</p>
      )}
      {state.status === 'error' && (
        <p className="calendar-status calendar-status--error" role="alert">
          날짜별 소비를 표시하지 못했습니다.
        </p>
      )}
    </section>
  )
}

function transactionTitle(transaction: LedgerTransaction) {
  if (transaction.type === 'TRANSFER') return '계좌 이체'
  if (transaction.adjustmentType === 'REFUND') {
    return `${transaction.category?.name ?? '지출'} 환불`
  }
  return transaction.category?.name ?? (transaction.type === 'INCOME' ? '수입' : '지출')
}

function transactionAmount(transaction: LedgerTransaction) {
  if (transaction.type === 'TRANSFER') return `↔ ${formatWon(transaction.amount)}`
  if (transaction.type === 'INCOME' || transaction.adjustmentType === 'REFUND') {
    return `+${formatWon(transaction.amount)}`
  }
  return `−${formatWon(transaction.amount)}`
}

function accountPath(transaction: LedgerTransaction) {
  if (transaction.type === 'TRANSFER') {
    return `${entryByRole(transaction, 'SOURCE')?.account.name ?? '출금 Account'} → ${entryByRole(transaction, 'DESTINATION')?.account.name ?? '입금 Account'}`
  }
  return entryByRole(transaction, 'PRIMARY')?.account.name ?? 'Account'
}

function RefundAction({
  transaction,
  refreshKey,
  onOpen,
}: {
  transaction: LedgerTransaction
  refreshKey: number
  onOpen: (
    transaction: LedgerTransaction,
    summary: RefundSummary,
    opener: HTMLElement,
  ) => void
}) {
  const [state, setState] = useState<AsyncState<RefundSummary>>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    void loadRefundSummary(transaction.id, controller.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [refreshKey, transaction.id])

  if (state.status === 'loading') {
    return <span className="refund-state">환불 정보 확인 중…</span>
  }
  if (state.status === 'error') {
    return <span className="refund-state refund-state--error">환불 정보 확인 실패</span>
  }
  if (state.data.remainingRefundableAmount === 0) {
    return <span className="refund-state">전액 환불됨</span>
  }
  return (
    <>
      <span className="refund-state">
        {state.data.refundedAmount > 0
          ? `${formatWon(state.data.refundedAmount)} 환불됨 · `
          : ''}
        {formatWon(state.data.remainingRefundableAmount)} 환불 가능
      </span>
      <button
        type="button"
        data-refund-opener={transaction.id}
        onClick={(event) => onOpen(transaction, state.data, event.currentTarget)}
      >
        환불
      </button>
    </>
  )
}

function SelectedDayTransactions({
  date,
  state,
  refreshKey,
  onEdit,
  onRefund,
  onDeleted,
}: {
  date: string
  state: AsyncState<LedgerTransaction[]>
  refreshKey: number
  onEdit: (transaction: LedgerTransaction, opener: HTMLElement) => void
  onRefund: (
    transaction: LedgerTransaction,
    summary: RefundSummary,
    opener: HTMLElement,
  ) => void
  onDeleted: () => void
}) {
  const [deleting, setDeleting] = useState<number | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function performDelete(transaction: LedgerTransaction) {
    setDeleting(transaction.id)
    setConfirmingDelete(null)
    setDeleteError(null)
    try {
      await deleteTransaction(transaction.id, transaction.version)
      onDeleted()
    } catch (error) {
      setDeleteError(errorMessage(error))
    } finally {
      setDeleting(null)
    }
  }

  return (
    <section className="selected-day" aria-labelledby="selected-day-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Selected Day</p>
          <h2 id="selected-day-title" tabIndex={-1}>
            {Number(date.slice(5, 7))}월 {Number(date.slice(8))}일의 기록
          </h2>
        </div>
        {state.status === 'ready' && <span className="count-badge">{state.data.length}</span>}
      </div>
      {state.status === 'loading' && (
        <p className="list-state" role="status">선택한 날짜의 거래를 불러오고 있어요.</p>
      )}
      {state.status === 'error' && (
        <p className="list-state list-state--error" role="alert">{state.message}</p>
      )}
      {state.status === 'ready' && state.data.length === 0 && (
        <p className="list-state">이 날짜에는 아직 거래가 없어요.</p>
      )}
      {state.status === 'ready' && state.data.length > 0 && (
        <ul className="transaction-list">
          {state.data.map((transaction) => (
            <li key={transaction.id}>
              <span className={`transaction-sign transaction-sign--${
                transaction.adjustmentType === 'REFUND'
                  ? 'refund'
                  : transaction.type.toLowerCase()
              }`}>
                {transaction.type === 'TRANSFER'
                  ? '↔'
                  : transaction.type === 'INCOME' || transaction.adjustmentType === 'REFUND'
                    ? '+'
                    : '−'}
              </span>
              <div className="transaction-copy">
                <strong>
                  {transactionTitle(transaction)}
                  {typeof transaction.generatedFromRecurringId === 'number' && (
                    <span className="provenance-badge">반복</span>
                  )}
                </strong>
                <span>
                  {transaction.adjustmentType === 'REFUND'
                    ? `${transaction.memo ? `${transaction.memo} · ` : ''}${accountPath(transaction)}`
                    : `${accountPath(transaction)} · ${transaction.scope === 'SHARED'
                      ? '공동'
                      : transaction.owner?.displayName ?? '이체'}`}
                </span>
                {transaction.adjustmentType === 'REFUND'
                  ? <small>원 지출을 상쇄한 환불 기록</small>
                  : transaction.memo && <small>{transaction.memo}</small>}
              </div>
              <b className={[
                'transaction-amount',
                transaction.adjustmentType === 'REFUND'
                  ? 'transaction-amount--refund'
                  : '',
              ].filter(Boolean).join(' ')}>
                {transactionAmount(transaction)}
              </b>
              <div className="transaction-actions">
                {transaction.type === 'EXPENSE'
                  && transaction.adjustmentType === 'NORMAL' && (
                    <RefundAction
                      transaction={transaction}
                      refreshKey={refreshKey}
                      onOpen={onRefund}
                    />
                  )}
                {transaction.adjustmentType !== 'REFUND' && (
                  <button
                    type="button"
                    onClick={(event) => onEdit(transaction, event.currentTarget)}
                  >
                    수정
                  </button>
                )}
                <button
                  type="button"
                  disabled={deleting === transaction.id}
                  onClick={() => {
                    if (transaction.adjustmentType === 'REFUND') {
                      setConfirmingDelete(transaction.id)
                    } else {
                      void performDelete(transaction)
                    }
                  }}
                >
                  {deleting === transaction.id ? '삭제 중…' : '삭제'}
                </button>
              </div>
              {confirmingDelete === transaction.id && (
                <div className="refund-delete-confirm" role="group" aria-label="환불 삭제 확인">
                  <p>환불 기록만 삭제되며 원 지출은 유지됩니다.</p>
                  <button
                    type="button"
                    disabled={deleting === transaction.id}
                    onClick={() => void performDelete(transaction)}
                  >
                    삭제 확인
                  </button>
                  <button type="button" onClick={() => setConfirmingDelete(null)}>
                    취소
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {deleteError && <p className="form-error" role="alert">{deleteError}</p>}
    </section>
  )
}

function BottomNavigation({
  active,
  onNavigate,
}: {
  active: WorkspaceScreen
  onNavigate: (destination: WorkspaceScreen) => void
}) {
  return (
    <nav className="bottom-navigation" aria-label="주요 메뉴">
      <button
        type="button"
        className={active === 'calendar' ? 'is-active' : ''}
        aria-current={active === 'calendar' ? 'page' : undefined}
        onClick={() => onNavigate('calendar')}
      >
        <span aria-hidden="true">▦</span>Calendar
      </button>
      <button
        type="button"
        className={active === 'budget' ? 'is-active' : ''}
        aria-current={active === 'budget' ? 'page' : undefined}
        onClick={() => onNavigate('budget')}
      >
        <span aria-hidden="true">◔</span>예산
      </button>
      <button
        type="button"
        className={active === 'statistics' ? 'is-active' : ''}
        aria-current={active === 'statistics' ? 'page' : undefined}
        onClick={() => onNavigate('statistics')}
      >
        <span aria-hidden="true">⌁</span>통계
      </button>
      <button type="button" disabled><span aria-hidden="true">◇</span>자산<span>준비 중</span></button>
    </nav>
  )
}

function CalendarWorkspace({
  user,
  initialReferences,
}: {
  user: CurrentUser
  initialReferences: ReferenceData
}) {
  const [references, setReferences] = useState(initialReferences)
  const [activeScreen, setActiveScreen] = useState<WorkspaceScreen>(() =>
    screenFromSearch(window.location.search))
  const [navigation, setNavigation] = useState(() =>
    normalizeCalendarState(window.location.search, initialReferences.household))
  const [budgetMonth, setBudgetMonth] = useState(() =>
    isBudgetScreen(window.location.search)
      ? normalizeBudgetMonth(window.location.search, initialReferences.household.timezone)
      : currentBudgetMonth(initialReferences.household.timezone))
  const [statisticsNavigation, setStatisticsNavigation] = useState<StatisticsNavigationState>(() =>
    normalizeStatisticsState(window.location.search, initialReferences.household))
  const [monthState, setMonthState] = useState<AsyncState<CalendarMonth>>({ status: 'loading' })
  const [dayState, setDayState] = useState<AsyncState<LedgerTransaction[]>>({ status: 'loading' })
  const [goalState, setGoalState] = useState<GoalViewState>({ status: 'loading' })
  const [goalRevision, setGoalRevision] = useState(0)
  const [revision, setRevision] = useState(0)
  const [entryMode, setEntryMode] = useState<{
    selectedDate: string
    editing: LedgerTransaction | null
  } | null>(null)
  const [refundMode, setRefundMode] = useState<{
    original: LedgerTransaction
    summary: RefundSummary
  } | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [goalSheet, setGoalSheet] = useState<'create' | 'edit' | 'link' | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const refundOpenerRef = useRef<HTMLElement | null>(null)
  const refundOriginalIdRef = useRef<number | null>(null)
  const settingsButtonRef = useRef<HTMLElement | null>(null)
  const goalOpenerRef = useRef<HTMLElement | null>(null)
  const calendarGoalFocusRef = useRef<HTMLButtonElement | null>(null)
  const goalDetailFocusRef = useRef<HTMLButtonElement | null>(null)
  const goalCreateContextRef = useRef<'calendar' | 'goal' | null>(null)
  const goalCreateSucceededRef = useRef(false)

  const filter = useMemo(() => calendarFilter(navigation), [navigation])
  const filterKey = `${filter.scope}:${filter.ownerMemberId ?? ''}`

  const finishClosingEntry = useCallback(() => {
    setEntryMode(null)
    window.setTimeout(() => openerRef.current?.focus(), 0)
  }, [])

  const requestCloseEntry = useCallback(() => {
    const ownsHistoryEntry = window.history.state?.ourLedgerSheet === 'quick-entry'
    finishClosingEntry()
    if (ownsHistoryEntry) window.history.back()
  }, [finishClosingEntry])

  const finishClosingRefund = useCallback(() => {
    const opener = refundOpenerRef.current
    const originalId = refundOriginalIdRef.current
    setRefundMode(null)
    window.setTimeout(() => {
      const currentOpener = originalId === null
        ? null
        : document.querySelector(`[data-refund-opener="${originalId}"]`)
      if (currentOpener instanceof HTMLElement) {
        currentOpener.focus()
      } else if (opener?.isConnected) {
        opener.focus()
      } else {
        document.getElementById('selected-day-title')?.focus()
      }
    }, 0)
  }, [])

  const requestCloseRefund = useCallback(() => {
    const ownsHistoryEntry = window.history.state?.ourLedgerSheet === 'refund'
    finishClosingRefund()
    if (ownsHistoryEntry) window.history.back()
  }, [finishClosingRefund])

  const finishClosingGoalSheet = useCallback(() => {
    const opener = goalOpenerRef.current
    const createContext = goalCreateContextRef.current
    const createSucceeded = goalCreateSucceededRef.current
    setGoalSheet(null)
    window.setTimeout(() => {
      if (opener?.isConnected) {
        opener.focus()
      } else if (createSucceeded) {
        const fallback = createContext === 'calendar'
          ? calendarGoalFocusRef.current
          : goalDetailFocusRef.current
        fallback?.focus()
      }
      goalCreateContextRef.current = null
      goalCreateSucceededRef.current = false
    }, 0)
  }, [])

  const requestCloseGoalSheet = useCallback(() => {
    const ownsHistoryEntry = window.history.state?.ourLedgerSheet === 'goal'
    finishClosingGoalSheet()
    if (ownsHistoryEntry) window.history.back()
  }, [finishClosingGoalSheet])

  useEffect(() => {
    if (activeScreen !== 'calendar') return
    const normalizedSearch = serializeCalendarState(navigation)
    if (window.location.search !== normalizedSearch) {
      window.history.replaceState(window.history.state, '', normalizedSearch)
    }
  }, [activeScreen, navigation])

  useEffect(() => {
    if (activeScreen !== 'budget') return
    const normalizedSearch = serializeBudgetState(budgetMonth)
    if (window.location.search !== normalizedSearch) {
      window.history.replaceState(window.history.state, '', normalizedSearch)
    }
  }, [activeScreen, budgetMonth])

  useEffect(() => {
    if (activeScreen !== 'statistics') return
    const normalizedSearch = serializeStatisticsState(statisticsNavigation)
    if (window.location.search !== normalizedSearch) {
      window.history.replaceState(window.history.state, '', normalizedSearch)
    }
  }, [activeScreen, statisticsNavigation])

  useEffect(() => {
    if (activeScreen !== 'goal') return
    const normalizedSearch = '?screen=goal'
    if (window.location.search !== normalizedSearch) {
      window.history.replaceState(window.history.state, '', normalizedSearch)
    }
  }, [activeScreen])

  useEffect(() => {
    const onPopState = () => {
      const nextScreen = screenFromSearch(window.location.search)
      setActiveScreen(nextScreen)
      if (nextScreen === 'budget') {
        const nextBudgetMonth = normalizeBudgetMonth(
          window.location.search,
          references.household.timezone,
        )
        const normalizedSearch = serializeBudgetState(nextBudgetMonth)
        if (window.location.search !== normalizedSearch) {
          window.history.replaceState(window.history.state, '', normalizedSearch)
        }
        setBudgetMonth(nextBudgetMonth)
      } else if (nextScreen === 'statistics') {
        const nextStatistics = normalizeStatisticsState(
          window.location.search,
          references.household,
        )
        const normalizedSearch = serializeStatisticsState(nextStatistics)
        if (window.location.search !== normalizedSearch) {
          window.history.replaceState(window.history.state, '', normalizedSearch)
        }
        setStatisticsNavigation(nextStatistics)
      } else if (nextScreen === 'goal') {
        // Goal has no additional URL state in Slice 8.
      } else {
        setNavigation(normalizeCalendarState(window.location.search, references.household))
      }
      if (entryMode && window.history.state?.ourLedgerSheet !== 'quick-entry') {
        finishClosingEntry()
      }
      if (refundMode && window.history.state?.ourLedgerSheet !== 'refund') {
        finishClosingRefund()
      }
      if (goalSheet && window.history.state?.ourLedgerSheet !== 'goal') {
        finishClosingGoalSheet()
      }
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [
    entryMode,
    finishClosingEntry,
    finishClosingRefund,
    finishClosingGoalSheet,
    goalSheet,
    references.household,
    refundMode,
  ])

  useEffect(() => {
    if (activeScreen !== 'calendar' && activeScreen !== 'goal') return
    const controller = new AbortController()
    setGoalState({ status: 'loading' })
    void loadMarriageGoal(controller.signal)
      .then((data) => setGoalState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setGoalState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [activeScreen, goalRevision, revision])

  useEffect(() => {
    if (activeScreen !== 'calendar') return
    const controller = new AbortController()
    setMonthState({ status: 'loading' })
    void loadCalendarMonth(navigation.month, filter, controller.signal)
      .then((data) => setMonthState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setMonthState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [activeScreen, filterKey, navigation.month, revision])

  useEffect(() => {
    if (activeScreen !== 'calendar') return
    const controller = new AbortController()
    setDayState({ status: 'loading' })
    void loadDayTransactions(navigation.date, filter, controller.signal)
      .then((data) => setDayState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setDayState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [activeScreen, filterKey, navigation.date, revision])

  function updateNavigation(next: CalendarNavigationState) {
    window.history.pushState({}, '', serializeCalendarState(next))
    setActiveScreen('calendar')
    setNavigation(next)
  }

  function openEntry(
    editing: LedgerTransaction | null,
    opener?: HTMLElement,
    selectedDate = activeScreen === 'calendar'
      ? navigation.date
      : todayInTimeZone(references.household.timezone),
  ) {
    openerRef.current = opener ?? (document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null)
    window.history.pushState(
      { ...window.history.state, ourLedgerSheet: 'quick-entry' },
      '',
      window.location.href,
    )
    setEntryMode({ selectedDate, editing })
  }

  function openRefund(
    original: LedgerTransaction,
    summary: RefundSummary,
    opener: HTMLElement,
  ) {
    refundOpenerRef.current = opener
    refundOriginalIdRef.current = original.id
    window.history.pushState(
      { ...window.history.state, ourLedgerSheet: 'refund' },
      '',
      window.location.href,
    )
    setRefundMode({ original, summary })
  }

  function openGoalSheet(mode: 'create' | 'edit' | 'link', opener: HTMLElement) {
    goalOpenerRef.current = opener
    goalCreateContextRef.current = mode === 'create'
      && (activeScreen === 'calendar' || activeScreen === 'goal')
      ? activeScreen
      : null
    goalCreateSucceededRef.current = false
    window.history.pushState(
      { ...window.history.state, ourLedgerSheet: 'goal' },
      '',
      window.location.href,
    )
    setGoalSheet(mode)
  }

  function navigate(destination: WorkspaceScreen) {
    if (destination === activeScreen) return
    if (destination === 'budget') {
      window.history.pushState({}, '', serializeBudgetState(budgetMonth))
      setActiveScreen('budget')
      return
    }
    if (destination === 'statistics') {
      window.history.pushState({}, '', serializeStatisticsState(statisticsNavigation))
      setActiveScreen('statistics')
      return
    }
    if (destination === 'goal') {
      window.history.pushState({}, '', '?screen=goal')
      setActiveScreen('goal')
      return
    }
    window.history.pushState({}, '', serializeCalendarState(navigation))
    setActiveScreen('calendar')
  }

  function moveBudget(offset: number) {
    const nextMonth = moveBudgetMonth(budgetMonth, offset)
    window.history.pushState({}, '', serializeBudgetState(nextMonth))
    setBudgetMonth(nextMonth)
  }

  function updateStatisticsNavigation(next: StatisticsNavigationState) {
    window.history.pushState({}, '', serializeStatisticsState(next))
    setStatisticsNavigation(next)
    setActiveScreen('statistics')
  }

  function closeSettings() {
    setSettingsOpen(false)
    window.setTimeout(() => settingsButtonRef.current?.focus(), 0)
  }

  async function refreshReferences() {
    const data = await loadReferenceData()
    setReferences(data)
    setRevision((current) => current + 1)
  }

  function acceptGoalView(view: MarriageGoalView) {
    if (goalSheet === 'create') goalCreateSucceededRef.current = true
    setGoalState({ status: 'ready', data: view })
  }

  async function unlinkGoalAccount(accountId: number) {
    await unlinkMarriageGoalAccount(accountId)
    setGoalRevision((current) => current + 1)
  }

  return (
    <>
      <main className="app-shell">
        <CoupleHeader
          user={user}
          household={references.household}
          onOpenSettings={() => {
            settingsButtonRef.current = document.activeElement instanceof HTMLElement
              ? document.activeElement
              : null
            setSettingsOpen(true)
          }}
        />
        {activeScreen === 'calendar' ? (
          <>
            <SpendingHero
              navigation={navigation}
              household={references.household}
              state={monthState}
              onRetry={() => setRevision((current) => current + 1)}
            />
            <MarriageGoalCard
              state={goalState}
              onRetry={() => setGoalRevision((current) => current + 1)}
              onOpen={() => navigate('goal')}
              onCreate={(opener) => openGoalSheet('create', opener)}
              createSuccessFocusRef={calendarGoalFocusRef}
            />
            <ScopeSelector
              user={user}
              household={references.household}
              navigation={navigation}
              onChange={updateNavigation}
            />
            <MonthNavigation
              month={navigation.month}
              onMove={(offset) => updateNavigation(moveCalendarMonth(navigation, offset))}
            />
            <CalendarGrid
              household={references.household}
              navigation={navigation}
              state={monthState}
              onSelect={(date) => updateNavigation({ ...navigation, date })}
            />
            <SelectedDayTransactions
              date={navigation.date}
              state={dayState}
              refreshKey={revision}
              onEdit={openEntry}
              onRefund={openRefund}
              onDeleted={() => setRevision((current) => current + 1)}
            />
          </>
        ) : activeScreen === 'goal' ? (
          <MarriageGoalScreen
            state={goalState}
            timezone={references.household.timezone}
            onBack={() => navigate('calendar')}
            onRetry={() => setGoalRevision((current) => current + 1)}
            onCreate={(opener) => openGoalSheet('create', opener)}
            onEdit={(opener) => openGoalSheet('edit', opener)}
            onLink={(opener) => openGoalSheet('link', opener)}
            onUnlink={unlinkGoalAccount}
            createSuccessFocusRef={goalDetailFocusRef}
          />
        ) : activeScreen === 'budget' ? (
          <BudgetScreen
            month={budgetMonth}
            household={references.household}
            categories={references.categories}
            revision={revision}
            onMoveMonth={moveBudget}
            onChanged={() => setRevision((current) => current + 1)}
          />
        ) : (
          <StatisticsScreen
            navigation={statisticsNavigation}
            household={references.household}
            revision={revision}
            onChange={updateStatisticsNavigation}
          />
        )}
      </main>
      <button
        className="paw-fab"
        type="button"
        aria-label={`${activeScreen === 'calendar'
          ? navigation.date
          : todayInTimeZone(references.household.timezone)} 빠른 입력 열기`}
        onClick={(event) => openEntry(null, event.currentTarget)}
      >
        <span aria-hidden="true">🐾</span>
        <small>기록</small>
      </button>
      <BottomNavigation active={activeScreen} onNavigate={navigate} />
      {entryMode && (
        <QuickEntrySheet
          currentUserId={user.userId}
          household={references.household}
          accounts={references.accounts}
          categories={references.categories}
          selectedDate={entryMode.selectedDate}
          editing={entryMode.editing}
          onRequestClose={requestCloseEntry}
          onSaved={() => setRevision((current) => current + 1)}
        />
      )}
      {refundMode && (
        <RefundSheet
          household={references.household}
          original={refundMode.original}
          initialSummary={refundMode.summary}
          onRequestClose={requestCloseRefund}
          onSaved={() => setRevision((current) => current + 1)}
        />
      )}
      {settingsOpen && (
        <SettingsSheet
          currentUserId={user.userId}
          household={references.household}
          accounts={references.accounts}
          groups={references.groups}
          categories={references.categories}
          onChanged={refreshReferences}
          onRequestClose={closeSettings}
        />
      )}
      {(goalSheet === 'create' || goalSheet === 'edit') && (
        <MarriageGoalSheet
          goal={goalSheet === 'edit' && goalState.status === 'ready'
            ? goalState.data.goal
            : null}
          onSaved={acceptGoalView}
          onRequestClose={requestCloseGoalSheet}
        />
      )}
      {goalSheet === 'link' && goalState.status === 'ready' && (
        <GoalAccountLinkSheet
          accounts={goalState.data.eligibleAccounts}
          onSaved={acceptGoalView}
          onRequestClose={requestCloseGoalSheet}
        />
      )}
    </>
  )
}

function CalendarLoader({ user }: { user: CurrentUser }) {
  const [state, setState] = useState<AsyncState<ReferenceData>>({ status: 'loading' })

  const load = useCallback(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    void loadReferenceData(controller.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return controller
  }, [])

  useEffect(() => {
    const controller = load()
    return () => controller.abort()
  }, [load])

  if (state.status === 'loading') {
    return (
      <main className="access-state" role="status">
        <span className="loading-paw" aria-hidden="true">🐾</span>
        <strong>Calendar를 준비하고 있어요.</strong>
      </main>
    )
  }
  if (state.status === 'error') {
    return (
      <main className="access-state access-state--error" role="alert">
        <strong>가계부를 불러오지 못했습니다.</strong>
        <span>{state.message}</span>
        <button type="button" onClick={load}>다시 시도</button>
      </main>
    )
  }
  return <CalendarWorkspace user={user} initialReferences={state.data} />
}

function App() {
  const [state, setState] = useState<ViewState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    void loadCurrentUser(controller.signal)
      .then((user) => setState({ status: 'ready', user }))
      .catch((error: unknown) => {
        if (isAbortError(error)) return
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

  if (state.status !== 'ready') return <AccessState state={state} />
  return <CalendarLoader user={state.user} />
}

export default App
