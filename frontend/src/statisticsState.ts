import type { CalendarFilter, CurrentHousehold } from './ledgerApi.ts'
import { todayInTimeZone } from './dateTime.ts'

export type StatisticsPreset =
  | 'this-month'
  | 'last-month'
  | 'recent-3-months'
  | 'recent-6-months'
  | 'year'
  | 'custom'

export type StatisticsView = 'all' | 'member' | 'shared'

export type StatisticsNavigationState = {
  preset: StatisticsPreset
  from: string
  to: string
  compareFrom: string
  compareTo: string
  view: StatisticsView
  memberId: number | null
}

const DATE_PATTERN = /^([1-9]\d{3})-(0[1-9]|1[0-2])-([0-2]\d|3[01])$/
const PRESETS: StatisticsPreset[] = [
  'this-month',
  'last-month',
  'recent-3-months',
  'recent-6-months',
  'year',
  'custom',
]

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10)
}

function parseDate(value: string) {
  const match = DATE_PATTERN.exec(value)
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  return isoDate(date) === value ? date : null
}

function monthStart(value: Date, offset = 0) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + offset, 1))
}

function monthEnd(value: Date, offset = 0) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + offset + 1, 0))
}

function previousRange(from: string, to: string) {
  const fromDate = parseDate(from)
  const toDate = parseDate(to)
  if (!fromDate || !toDate) throw new Error('유효한 기간이 필요합니다.')
  const day = 24 * 60 * 60 * 1000
  const dayCount = Math.round((toDate.getTime() - fromDate.getTime()) / day) + 1
  const compareTo = new Date(fromDate.getTime() - day)
  const compareFrom = new Date(compareTo.getTime() - (dayCount - 1) * day)
  return { compareFrom: isoDate(compareFrom), compareTo: isoDate(compareTo) }
}

export function presetRange(
  preset: Exclude<StatisticsPreset, 'custom'>,
  timezone: string,
  now = new Date(),
) {
  const today = parseDate(todayInTimeZone(timezone, now)) as Date
  let from: Date
  let to: Date
  let monthCount: number
  if (preset === 'last-month') {
    monthCount = 1
    from = monthStart(today, -1)
    to = monthEnd(today, -1)
  } else {
    monthCount = preset === 'recent-3-months'
      ? 3
      : preset === 'recent-6-months'
        ? 6
        : preset === 'year'
          ? 12
          : 1
    from = monthStart(today, -(monthCount - 1))
    to = monthEnd(today)
  }
  const range = { from: isoDate(from), to: isoDate(to) }
  return {
    ...range,
    compareFrom: isoDate(monthStart(from, -monthCount)),
    compareTo: isoDate(monthEnd(from, -1)),
  }
}

export function isStatisticsScreen(search: string) {
  return new URLSearchParams(search).get('screen') === 'statistics'
}

export function normalizeStatisticsState(
  search: string,
  household: CurrentHousehold,
  now = new Date(),
): StatisticsNavigationState {
  const parameters = new URLSearchParams(search)
  const requestedPreset = parameters.get('preset') as StatisticsPreset | null
  let preset = requestedPreset && PRESETS.includes(requestedPreset)
    ? requestedPreset
    : 'this-month'
  let range: ReturnType<typeof presetRange>

  if (preset === 'custom') {
    const from = parameters.get('from') ?? ''
    const to = parameters.get('to') ?? ''
    if (parseDate(from) && parseDate(to) && from <= to) {
      range = { from, to, ...previousRange(from, to) }
    } else {
      preset = 'this-month'
      range = presetRange('this-month', household.timezone, now)
    }
  } else {
    range = presetRange(preset, household.timezone, now)
  }

  const requestedView = parameters.get('view')
  const requestedMemberId = Number(parameters.get('memberId'))
  const member = household.members.find((item) => item.memberId === requestedMemberId)
  if (requestedView === 'member' && member) {
    return { preset, ...range, view: 'member', memberId: member.memberId }
  }
  if (requestedView === 'shared') {
    return { preset, ...range, view: 'shared', memberId: null }
  }
  return { preset, ...range, view: 'all', memberId: null }
}

export function withStatisticsPreset(
  state: StatisticsNavigationState,
  preset: StatisticsPreset,
  household: CurrentHousehold,
  custom?: { from: string; to: string },
): StatisticsNavigationState | null {
  if (preset === 'custom') {
    if (!custom || !parseDate(custom.from) || !parseDate(custom.to) || custom.from > custom.to) {
      return null
    }
    return {
      ...state,
      preset,
      ...custom,
      ...previousRange(custom.from, custom.to),
    }
  }
  return { ...state, preset, ...presetRange(preset, household.timezone) }
}

export function serializeStatisticsState(state: StatisticsNavigationState) {
  const parameters = new URLSearchParams({
    screen: 'statistics',
    preset: state.preset,
    view: state.view,
  })
  if (state.preset === 'custom') {
    parameters.set('from', state.from)
    parameters.set('to', state.to)
  }
  if (state.view === 'member' && state.memberId !== null) {
    parameters.set('memberId', state.memberId.toString())
  }
  return `?${parameters}`
}

export function statisticsFilter(state: StatisticsNavigationState): CalendarFilter {
  if (state.view === 'member' && state.memberId !== null) {
    return { scope: 'PERSONAL', ownerMemberId: state.memberId }
  }
  if (state.view === 'shared') {
    return { scope: 'SHARED', ownerMemberId: null }
  }
  return { scope: 'ALL', ownerMemberId: null }
}
