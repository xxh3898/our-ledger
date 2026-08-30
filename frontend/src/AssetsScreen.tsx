import type { AssetsData, AssetsSummary } from './ledgerApi.ts'
import type { AssetsNavigationState } from './assetsState.ts'

export type AssetsViewState =
  | { status: 'loading' }
  | { status: 'ready'; data: AssetsData }
  | { status: 'error'; message: string }

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

function monthLabel(month: string, complete: boolean) {
  const [year, monthNumber] = month.split('-').map(Number)
  return complete ? `${year}년 ${monthNumber}월` : `${year}년 ${monthNumber}월 현재`
}

function TrendChart({ trend }: { trend: AssetsData['monthlyTrend'] }) {
  const values = trend.map((point) => point.netWorth)
  const minimum = Math.min(...values, 0)
  const maximum = Math.max(...values, 0)
  const range = maximum - minimum || 1
  const points = values.map((value, index) => {
    const x = 6 + (index * 88) / Math.max(values.length - 1, 1)
    const y = 56 - ((value - minimum) / range) * 46
    return `${x},${y}`
  }).join(' ')

  return (
    <div className="assets-trend">
      <svg viewBox="0 0 100 64" role="img" aria-labelledby="assets-trend-title">
        <title id="assets-trend-title">우리 전체 최근 11개 완료 월말과 현재 순자산 추이</title>
        <line x1="6" y1="56" x2="94" y2="56" />
        <polyline points={points} />
        {points.split(' ').map((point, index) => {
          const [cx, cy] = point.split(',')
          return (
            <circle
              className={trend[index].complete ? undefined : 'is-current'}
              key={`${trend[index].month}:${trend[index].complete}`}
              cx={cx}
              cy={cy}
              r={trend[index].complete ? '1.7' : '2.5'}
            />
          )
        })}
      </svg>
      <p className="assets-trend-legend"><span aria-hidden="true" />순자산 · 마지막 점은 현재</p>
      <div className="assets-table-wrap">
        <table>
          <caption>우리 전체 월별 자산·부채·순자산</caption>
          <thead><tr><th>월</th><th>자산</th><th>부채</th><th>순자산</th></tr></thead>
          <tbody>
            {trend.map((point) => (
              <tr key={`${point.month}:${point.complete}`}>
                <th scope="row">
                  {monthLabel(point.month, point.complete)}
                  {!point.complete && <small>진행 중</small>}
                </th>
                <td>{formatWon(point.assets)}</td>
                <td>{formatWon(point.liabilities)}</td>
                <td>{formatWon(point.netWorth)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function selectedSummary(
  data: AssetsData,
  navigation: AssetsNavigationState,
): AssetsSummary {
  if (navigation.view === 'shared') return data.shared
  if (navigation.view === 'personal') {
    return data.members.find((member) => member.memberId === navigation.memberId)
      ?? { totalAssets: 0, totalLiabilities: 0, netWorth: 0 }
  }
  return data.household
}

function selectionLabel(data: AssetsData, navigation: AssetsNavigationState) {
  if (navigation.view === 'shared') return '공동'
  if (navigation.view === 'personal') {
    return data.members.find((member) => member.memberId === navigation.memberId)
      ?.displayName ?? '개인'
  }
  return '우리 전체'
}

function filterAccounts(data: AssetsData, navigation: AssetsNavigationState) {
  if (navigation.view === 'shared') {
    return data.accounts.filter((account) => account.ownership === 'SHARED')
  }
  if (navigation.view === 'personal') {
    return data.accounts.filter((account) =>
      account.ownership === 'PERSONAL'
      && account.owner?.memberId === navigation.memberId)
  }
  return data.accounts
}

function AccountGroup({
  title,
  accounts,
}: {
  title: string
  accounts: AssetsData['accounts']
}) {
  const id = `assets-${title === 'ASSET Account' ? 'asset' : 'liability'}-title`
  return (
    <section className="assets-section assets-account-section" aria-labelledby={id}>
      <div className="section-heading">
        <div><p className="section-kicker">Current ledger</p><h2 id={id}>{title}</h2></div>
        <span>{accounts.length}개</span>
      </div>
      {accounts.length === 0 ? (
        <p className="list-state">{title}가 없어요.</p>
      ) : (
        <ul className="assets-account-list">
          {accounts.map((account) => (
            <li key={account.id}>
              <div>
                <strong>
                  {account.name}
                  {account.savingsEnabled && <span className="assets-badge">저축</span>}
                  {account.archived && <span className="assets-badge is-archived">보관됨</span>}
                </strong>
                <small>
                  {account.institution ?? account.type} · {account.ownership === 'SHARED'
                    ? '공동'
                    : account.owner?.displayName ?? '개인'}
                </small>
              </div>
              <div className="assets-account-balance">
                <small>{account.nature === 'LIABILITY' ? '부채 잔액' : '자산 잔액'}</small>
                <b>{formatWon(account.currentBalance)}</b>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

export function AssetsScreen({
  state,
  navigation,
  onChange,
  onRetry,
  onManageAccounts,
}: {
  state: AssetsViewState
  navigation: AssetsNavigationState
  onChange: (state: AssetsNavigationState) => void
  onRetry: () => void
  onManageAccounts: (opener: HTMLElement) => void
}) {
  if (state.status === 'loading') {
    return <section className="assets-page-state" role="status">자산 원장을 계산하고 있어요.</section>
  }
  if (state.status === 'error') {
    return (
      <section className="assets-page-state inline-error" role="alert">
        <span>{state.message}</span>
        <button type="button" onClick={onRetry}>다시 불러오기</button>
      </section>
    )
  }

  const data = state.data
  const summary = selectedSummary(data, navigation)
  const label = selectionLabel(data, navigation)
  const accounts = filterAccounts(data, navigation)
  const assetAccounts = accounts.filter((account) => account.nature === 'ASSET')
  const liabilityAccounts = accounts.filter((account) => account.nature === 'LIABILITY')

  return (
    <div className="assets-screen">
      <section className="assets-hero" aria-labelledby="assets-title">
        <p className="section-kicker">Actual ledger</p>
        <h2 id="assets-title">우리 순자산</h2>
        <strong>{formatWon(data.household.netWorth)}</strong>
        <dl>
          <div><dt>자산</dt><dd>{formatWon(data.household.totalAssets)}</dd></div>
          <div><dt>부채</dt><dd>{formatWon(data.household.totalLiabilities)}</dd></div>
        </dl>
      </section>

      <section className="assets-section" aria-labelledby="assets-trend-heading">
        <div className="section-heading">
          <div>
            <p className="section-kicker">12 snapshots</p>
            <h2 id="assets-trend-heading">우리 전체 순자산 추이</h2>
          </div>
        </div>
        <p className="assets-section-copy">소유 filter와 무관한 Household 전체 월말·현재 원장이에요.</p>
        <TrendChart trend={data.monthlyTrend} />
      </section>

      <nav className="assets-scope-selector" aria-label="현재 자산 소유 기준">
        <button
          type="button"
          aria-pressed={navigation.view === 'all'}
          onClick={() => onChange({ view: 'all', memberId: null })}
        >전체</button>
        {data.members.map((member) => (
          <button
            key={member.memberId}
            type="button"
            aria-pressed={navigation.view === 'personal'
              && navigation.memberId === member.memberId}
            onClick={() => onChange({ view: 'personal', memberId: member.memberId })}
          >{member.displayName}</button>
        ))}
        <button
          type="button"
          aria-pressed={navigation.view === 'shared'}
          onClick={() => onChange({ view: 'shared', memberId: null })}
        >공동</button>
      </nav>

      <section className="assets-current-summary" aria-labelledby="assets-current-title">
        <div className="section-heading">
          <div><p className="section-kicker">Current ownership</p><h2 id="assets-current-title">{label} 현재</h2></div>
        </div>
        <dl>
          <div><dt>자산</dt><dd>{formatWon(summary.totalAssets)}</dd></div>
          <div><dt>부채</dt><dd>{formatWon(summary.totalLiabilities)}</dd></div>
          <div><dt>순자산</dt><dd>{formatWon(summary.netWorth)}</dd></div>
        </dl>
      </section>

      {data.accounts.length === 0 && (
        <p className="assets-empty-state">아직 Account가 없어요. Account 관리에서 첫 계좌를 만들어 주세요.</p>
      )}
      {data.accounts.length > 0 && accounts.length === 0 && (
        <p className="assets-empty-state">선택한 소유 기준 Account가 없어요.</p>
      )}
      <AccountGroup title="ASSET Account" accounts={assetAccounts} />
      <AccountGroup title="LIABILITY Account" accounts={liabilityAccounts} />

      <section className="assets-manage-card">
        <div><strong>Account 관리</strong><p>생성·수정·보관은 기존 Settings에서 관리해요.</p></div>
        <button type="button" onClick={(event) => onManageAccounts(event.currentTarget)}>
          Account 관리 열기
        </button>
      </section>
    </div>
  )
}
