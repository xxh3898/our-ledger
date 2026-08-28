import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  type CalendarFilter,
  type CurrentHousehold,
  LedgerApiError,
  type StatisticsData,
  loadStatistics,
} from './ledgerApi.ts'
import {
  StatisticsDrilldownSheet,
  type StatisticsDrilldownTarget,
} from './StatisticsDrilldownSheet.tsx'
import {
  type StatisticsNavigationState,
  type StatisticsPreset,
  statisticsFilter,
  withStatisticsPreset,
} from './statisticsState.ts'

type State =
  | { status: 'loading' }
  | { status: 'ready'; data: StatisticsData }
  | { status: 'error'; message: string }

const PRESET_LABELS: Record<StatisticsPreset, string> = {
  'this-month': '이번 달',
  'last-month': '지난달',
  'recent-3-months': '최근 3개월',
  'recent-6-months': '최근 6개월',
  year: '1년',
  custom: '직접 선택',
}

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '통계를 불러오지 못했습니다.'
}

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function formatRate(rate: number | null) {
  return rate === null ? '계산 불가' : `${rate.toLocaleString('ko-KR')}%`
}

function differenceText(amount: number, percent: number | null) {
  const amountDirection = amount > 0 ? '증가' : amount < 0 ? '감소' : '변화 없음'
  const amountText = amount === 0 ? '0원' : `${formatWon(Math.abs(amount))} ${amountDirection}`
  if (percent === null) return `${amountText} · 비율 계산 불가`
  const percentDirection = percent > 0 ? '증가' : percent < 0 ? '감소' : '변화 없음'
  return `${amountText} · ${Math.abs(percent)}% ${percentDirection}`
}

function scopeFilter(
  scope: 'PERSONAL' | 'SHARED',
  ownerMemberId: number | null,
): CalendarFilter {
  if (scope === 'PERSONAL' && ownerMemberId !== null) {
    return { scope: 'PERSONAL', ownerMemberId }
  }
  return { scope: 'SHARED', ownerMemberId: null }
}

function SummaryCard({
  label,
  value,
  detail,
  onClick,
}: {
  label: string
  value: string
  detail?: string
  onClick?: (opener: HTMLElement) => void
}) {
  const content = (
    <>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </>
  )
  return onClick ? (
    <button
      className="statistics-summary-card"
      type="button"
      onClick={(event) => onClick(event.currentTarget)}
    >
      {content}
      <em>원장 보기</em>
    </button>
  ) : <div className="statistics-summary-card">{content}</div>
}

export function StatisticsScreen({
  navigation,
  household,
  revision,
  onChange,
}: {
  navigation: StatisticsNavigationState
  household: CurrentHousehold
  revision: number
  onChange: (state: StatisticsNavigationState) => void
}) {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [retryRevision, setRetryRevision] = useState(0)
  const [selectedPreset, setSelectedPreset] = useState<StatisticsPreset>(navigation.preset)
  const [customFrom, setCustomFrom] = useState(navigation.from)
  const [customTo, setCustomTo] = useState(navigation.to)
  const [customError, setCustomError] = useState('')
  const [drilldown, setDrilldown] = useState<StatisticsDrilldownTarget | null>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const filter = useMemo(() => statisticsFilter(navigation), [navigation])
  const filterKey = `${filter.scope}:${filter.ownerMemberId ?? ''}`
  const range = useMemo(() => ({ from: navigation.from, to: navigation.to }), [
    navigation.from,
    navigation.to,
  ])

  useEffect(() => {
    setSelectedPreset(navigation.preset)
    setCustomFrom(navigation.from)
    setCustomTo(navigation.to)
    setCustomError('')
  }, [navigation])

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    void loadStatistics({
      from: navigation.from,
      to: navigation.to,
      compareFrom: navigation.compareFrom,
      compareTo: navigation.compareTo,
    }, filter, controller.signal)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState({ status: 'error', message: errorMessage(error) })
        }
      })
    return () => controller.abort()
  }, [filterKey, navigation.compareFrom, navigation.compareTo, navigation.from,
    navigation.to, retryRevision, revision])

  const closeDrilldown = useCallback(() => {
    setDrilldown(null)
    window.setTimeout(() => openerRef.current?.focus(), 0)
  }, [])

  function openDrilldown(target: StatisticsDrilldownTarget, opener: HTMLElement) {
    openerRef.current = opener
    setDrilldown(target)
  }

  function choosePreset(preset: StatisticsPreset) {
    setSelectedPreset(preset)
    setCustomError('')
    if (preset === 'custom') return
    const next = withStatisticsPreset(navigation, preset, household)
    if (next) onChange(next)
  }

  function applyCustomRange() {
    const next = withStatisticsPreset(
      navigation,
      'custom',
      household,
      { from: customFrom, to: customTo },
    )
    if (!next) {
      setCustomError('시작일이 종료일보다 늦지 않은 실제 날짜를 입력해 주세요.')
      return
    }
    onChange(next)
  }

  function updateView(view: StatisticsNavigationState['view'], memberId: number | null) {
    onChange({ ...navigation, view, memberId })
  }

  return (
    <>
      <section className="statistics-heading" aria-labelledby="statistics-title">
        <p className="section-kicker">Slice 6 · Ledger Statistics</p>
        <h2 id="statistics-title">통계</h2>
        <p>저장된 원장에서 기간별 수입, 순소비와 저축 흐름을 계산합니다.</p>
      </section>

      <section className="statistics-controls" aria-label="통계 조건">
        <label>
          기간
          <select
            aria-label="통계 기간"
            value={selectedPreset}
            onChange={(event) => choosePreset(event.target.value as StatisticsPreset)}
          >
            {Object.entries(PRESET_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        {selectedPreset === 'custom' && (
          <div className="statistics-custom-range">
            <label>시작일<input type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} /></label>
            <label>종료일<input type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} /></label>
            <button type="button" onClick={applyCustomRange}>기간 적용</button>
            {customError && <p className="form-error" role="alert">{customError}</p>}
          </div>
        )}
        <p className="statistics-period-copy">{navigation.from} ~ {navigation.to}</p>
      </section>

      <nav className="scope-selector statistics-scope-selector" aria-label="통계 보기 범위">
        <button
          type="button"
          className={navigation.view === 'all' ? 'is-active' : ''}
          aria-pressed={navigation.view === 'all'}
          onClick={() => updateView('all', null)}
        >전체</button>
        {household.members.map((member) => (
          <button
            key={member.memberId}
            type="button"
            className={navigation.view === 'member' && navigation.memberId === member.memberId ? 'is-active' : ''}
            aria-pressed={navigation.view === 'member' && navigation.memberId === member.memberId}
            onClick={() => updateView('member', member.memberId)}
          >{member.displayName}</button>
        ))}
        <button
          type="button"
          className={navigation.view === 'shared' ? 'is-active' : ''}
          aria-pressed={navigation.view === 'shared'}
          onClick={() => updateView('shared', null)}
        >공동</button>
      </nav>

      {state.status === 'loading' && (
        <p className="statistics-page-state" role="status">선택한 조건의 통계를 계산하고 있어요.</p>
      )}
      {state.status === 'error' && (
        <div className="inline-error statistics-page-state" role="alert">
          <span>{state.message}</span>
          <button type="button" onClick={() => setRetryRevision((value) => value + 1)}>
            다시 불러오기
          </button>
        </div>
      )}
      {state.status === 'ready' && (
        <StatisticsContent
          data={state.data}
          filter={filter}
          savingsAvailable={navigation.view === 'all'}
          onDrilldown={openDrilldown}
        />
      )}

      {drilldown && (
        <StatisticsDrilldownSheet
          range={range}
          timezone={household.timezone}
          target={drilldown}
          onRequestClose={closeDrilldown}
        />
      )}
    </>
  )
}

function StatisticsContent({
  data,
  filter,
  savingsAvailable,
  onDrilldown,
}: {
  data: StatisticsData
  filter: CalendarFilter
  savingsAvailable: boolean
  onDrilldown: (target: StatisticsDrilldownTarget, opener: HTMLElement) => void
}) {
  return (
    <>
      <section className="statistics-section" aria-labelledby="statistics-summary-title">
        <div className="section-heading">
          <div><p className="section-kicker">Summary</p><h2 id="statistics-summary-title">이번 기간 요약</h2></div>
        </div>
        <div className="statistics-summary-grid">
          <SummaryCard
            label="수입"
            value={formatWon(data.summary.incomeAmount)}
            onClick={(opener) => onDrilldown({
              kind: 'transactions', title: '수입 원장', type: 'INCOME', filter,
            }, opener)}
          />
          <SummaryCard
            label="순소비"
            value={formatWon(data.summary.netSpendingAmount)}
            detail="지출에서 환불을 뺀 금액"
            onClick={(opener) => onDrilldown({
              kind: 'transactions', title: '소비·환불 원장', type: 'EXPENSE', filter,
            }, opener)}
          />
          {savingsAvailable ? (
            <>
              <SummaryCard
                label="저축"
                value={data.summary.savingsAmount === null
                  ? '계산 불가'
                  : formatWon(data.summary.savingsAmount)}
                detail="저축 Account 순이체"
                onClick={(opener) => onDrilldown({
                  kind: 'savings', title: '저축 활동',
                }, opener)}
              />
              <SummaryCard label="저축률" value={formatRate(data.summary.savingsRate)} />
            </>
          ) : (
            <div className="statistics-savings-unavailable">
              <strong>저축·저축률은 전체 보기에서 제공해요.</strong>
              <span>저축은 Account 간 이체 기준이라 개인·공동으로 임의 귀속하지 않아요.</span>
            </div>
          )}
        </div>
      </section>

      {data.comparison && (
        <section className="statistics-section" aria-labelledby="statistics-comparison-title">
          <div className="section-heading">
            <div>
              <p className="section-kicker">{data.comparison.from} ~ {data.comparison.to}</p>
              <h2 id="statistics-comparison-title">이전 기간과 비교</h2>
            </div>
          </div>
          <dl className="statistics-comparison-list">
            <div><dt>수입</dt><dd>{differenceText(data.comparison.incomeDifferenceAmount, data.comparison.incomePercentChange)}</dd></div>
            <div><dt>순소비</dt><dd>{differenceText(data.comparison.netSpendingDifferenceAmount, data.comparison.netSpendingPercentChange)}</dd></div>
            {savingsAvailable && data.comparison.savingsDifferenceAmount !== null && (
              <div><dt>저축</dt><dd>{differenceText(data.comparison.savingsDifferenceAmount, data.comparison.savingsPercentChange)}</dd></div>
            )}
            {savingsAvailable && (
              <div>
                <dt>저축률</dt>
                <dd>{data.comparison.savingsRateDifferencePoints === null
                  ? '비교 계산 불가'
                  : `${Math.abs(data.comparison.savingsRateDifferencePoints)}%p ${data.comparison.savingsRateDifferencePoints > 0 ? '증가' : data.comparison.savingsRateDifferencePoints < 0 ? '감소' : '변화 없음'}`}</dd>
              </div>
            )}
          </dl>
        </section>
      )}

      <section className="statistics-section" aria-labelledby="statistics-month-title">
        <div className="section-heading"><div><p className="section-kicker">Trend</p><h2 id="statistics-month-title">월별 추이</h2></div></div>
        <div className="statistics-table-wrap">
          <table className="statistics-table">
            <thead><tr><th>월</th><th>수입</th><th>순소비</th><th>저축</th><th>저축률</th></tr></thead>
            <tbody>
              {data.months.map((month) => (
                <tr key={month.month}>
                  <th>{month.month}</th>
                  <td>{formatWon(month.incomeAmount)}</td>
                  <td>{formatWon(month.netSpendingAmount)}</td>
                  <td>{!savingsAvailable
                    ? '전체 보기 전용'
                    : month.savingsAmount === null
                      ? '계산 불가'
                      : formatWon(month.savingsAmount)}</td>
                  <td>{!savingsAvailable ? '전체 보기 전용' : formatRate(month.savingsRate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <BreakdownSection title="어디에 썼나요" kicker="Category" empty="이 기간의 순소비 Category가 없어요.">
        {data.categories.map((item) => (
          <button
            key={item.category.id}
            type="button"
            onClick={(event) => onDrilldown({
              kind: 'transactions',
              title: `${item.category.name} 소비·환불`,
              type: 'EXPENSE',
              filter,
              categoryId: item.category.id,
            }, event.currentTarget)}
          >
            <span><strong>{item.category.name}</strong>{item.category.archived && <small>보관됨</small>}</span>
            <span><b>{formatWon(item.netSpendingAmount)}</b><small>{item.shareRate === null ? '비율 계산 불가' : `${item.shareRate}%`}</small></span>
          </button>
        ))}
      </BreakdownSection>

      <BreakdownSection title="누가 썼나요" kicker="Subject" empty="이 기간의 주체별 순소비가 없어요.">
        {data.subjects.map((item) => {
          const label = item.scope === 'SHARED' ? '공동' : item.owner?.displayName ?? '개인'
          return (
            <button
              key={`${item.scope}:${item.owner?.memberId ?? 'shared'}`}
              type="button"
              onClick={(event) => onDrilldown({
                kind: 'transactions',
                title: `${label} 소비·환불`,
                type: 'EXPENSE',
                filter: scopeFilter(item.scope, item.owner?.memberId ?? null),
              }, event.currentTarget)}
            >
              <span><strong>{label}</strong><small>{item.scope}</small></span>
              <b>{formatWon(item.netSpendingAmount)}</b>
            </button>
          )
        })}
      </BreakdownSection>

      <BreakdownSection title="어떤 Account로 썼나요" kicker="Account" empty="이 기간의 Account별 순소비가 없어요.">
        {data.accounts.map((item) => (
          <button
            key={item.account.id}
            type="button"
            onClick={(event) => onDrilldown({
              kind: 'transactions',
              title: `${item.account.name} 소비·환불`,
              type: 'EXPENSE',
              filter,
              accountId: item.account.id,
            }, event.currentTarget)}
          >
            <span>
              <strong>{item.account.name}</strong>
              <small>{item.account.type} · {item.account.nature}{item.account.archived ? ' · 보관됨' : ''}</small>
            </span>
            <b>{formatWon(item.netSpendingAmount)}</b>
          </button>
        ))}
      </BreakdownSection>
    </>
  )
}

function BreakdownSection({
  title,
  kicker,
  empty,
  children,
}: {
  title: string
  kicker: string
  empty: string
  children: React.ReactNode
}) {
  const items = Array.isArray(children) ? children : [children]
  const hasItems = items.some(Boolean)
  const id = `statistics-${kicker.toLowerCase()}-title`
  return (
    <section className="statistics-section statistics-breakdown" aria-labelledby={id}>
      <div className="section-heading"><div><p className="section-kicker">{kicker}</p><h2 id={id}>{title}</h2></div></div>
      {!hasItems && <p className="list-state">{empty}</p>}
      {hasItems && <div className="statistics-breakdown-list">{children}</div>}
    </section>
  )
}
