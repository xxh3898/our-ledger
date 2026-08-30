import type { CalendarFilter, CurrentHousehold } from './ledgerApi.ts'
import { todayInTimeZone } from './dateTime.ts'

export type CalendarView = 'all' | 'member' | 'shared'

export type CalendarNavigationState = {
  month: string
  date: string
  view: CalendarView
  memberId: number | null
}

const MONTH_PATTERN = /^[1-9]\d{3}-(0[1-9]|1[0-2])$/
const DATE_PATTERN = /^[1-9]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/

function monthParts(month: string) {
  const [year, number] = month.split('-').map(Number)
  return { year, number }
}

export function daysInMonth(month: string) {
  const { year, number } = monthParts(month)
  return new Date(Date.UTC(year, number, 0)).getUTCDate()
}

function dateBelongsToMonth(date: string, month: string) {
  if (!DATE_PATTERN.test(date) || !date.startsWith(`${month}-`)) return false
  const day = Number(date.slice(-2))
  return day <= daysInMonth(month)
}

function fallbackDate(month: string, today: string) {
  return today.startsWith(`${month}-`) ? today : `${month}-01`
}

export function normalizeCalendarState(
  search: string,
  household: CurrentHousehold,
  now = new Date(),
): CalendarNavigationState {
  const parameters = new URLSearchParams(search)
  const today = todayInTimeZone(household.timezone, now)
  const requestedMonth = parameters.get('month') ?? ''
  const month = MONTH_PATTERN.test(requestedMonth) ? requestedMonth : today.slice(0, 7)
  const requestedDate = parameters.get('date') ?? ''
  const date = dateBelongsToMonth(requestedDate, month)
    ? requestedDate
    : fallbackDate(month, today)
  const requestedView = parameters.get('view')
  const requestedMemberId = Number(parameters.get('memberId'))
  const member = household.members.find((item) => item.memberId === requestedMemberId)

  if (requestedView === 'member' && member) {
    return { month, date, view: 'member', memberId: member.memberId }
  }
  if (requestedView === 'shared') {
    return { month, date, view: 'shared', memberId: null }
  }
  return { month, date, view: 'all', memberId: null }
}

export function serializeCalendarState(state: CalendarNavigationState) {
  const parameters = new URLSearchParams({
    month: state.month,
    view: state.view,
    date: state.date,
  })
  if (state.view === 'member' && state.memberId !== null) {
    parameters.set('memberId', state.memberId.toString())
  }
  return `?${parameters}`
}

export function moveCalendarMonth(
  state: CalendarNavigationState,
  offset: number,
): CalendarNavigationState {
  const { year, number } = monthParts(state.month)
  const moved = new Date(Date.UTC(year, number - 1 + offset, 1))
  const month = `${moved.getUTCFullYear()}-${String(moved.getUTCMonth() + 1).padStart(2, '0')}`
  const selectedDay = Math.min(Number(state.date.slice(-2)), daysInMonth(month))
  return {
    ...state,
    month,
    date: `${month}-${String(selectedDay).padStart(2, '0')}`,
  }
}

export function calendarFilter(state: CalendarNavigationState): CalendarFilter {
  if (state.view === 'member' && state.memberId !== null) {
    return { scope: 'PERSONAL', ownerMemberId: state.memberId }
  }
  if (state.view === 'shared') {
    return { scope: 'SHARED', ownerMemberId: null }
  }
  return { scope: 'ALL', ownerMemberId: null }
}

export function calendarDates(month: string) {
  const { year, number } = monthParts(month)
  const leadingEmptyDays = new Date(Date.UTC(year, number - 1, 1)).getUTCDay()
  const dates: Array<string | null> = Array.from({ length: leadingEmptyDays }, () => null)
  for (let day = 1; day <= daysInMonth(month); day += 1) {
    dates.push(`${month}-${String(day).padStart(2, '0')}`)
  }
  while (dates.length % 7 !== 0) dates.push(null)
  return dates
}
