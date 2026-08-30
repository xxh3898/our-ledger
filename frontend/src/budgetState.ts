import { todayInTimeZone } from './dateTime.ts'

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/

export function isBudgetScreen(search: string) {
  return new URLSearchParams(search).get('screen') === 'budget'
}

export function currentBudgetMonth(timezone: string) {
  return todayInTimeZone(timezone).slice(0, 7)
}

export function normalizeBudgetMonth(search: string, timezone: string) {
  const month = new URLSearchParams(search).get('month')
  return month && MONTH_PATTERN.test(month) ? month : currentBudgetMonth(timezone)
}

export function serializeBudgetState(month: string) {
  const parameters = new URLSearchParams({ screen: 'budget', month })
  return `?${parameters}`
}

export function moveBudgetMonth(month: string, offset: number) {
  const [year, monthNumber] = month.split('-').map(Number)
  const moved = new Date(Date.UTC(year, monthNumber - 1 + offset, 1))
  return `${moved.getUTCFullYear()}-${String(moved.getUTCMonth() + 1).padStart(2, '0')}`
}
