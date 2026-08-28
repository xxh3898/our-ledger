import { describe, expect, it } from 'vitest'
import {
  calendarDates,
  calendarFilter,
  moveCalendarMonth,
  normalizeCalendarState,
  serializeCalendarState,
} from './calendarState.ts'

const household = {
  householdId: 10,
  name: '테스트 Household',
  baseCurrency: 'KRW',
  timezone: 'Asia/Seoul',
  members: [
    { memberId: 100, userId: 1, displayName: 'Owner', role: 'OWNER' as const },
    { memberId: 101, userId: 2, displayName: 'Member', role: 'MEMBER' as const },
  ],
}

describe('calendarState', () => {
  it('uses the Household timezone date when URL state is absent', () => {
    const state = normalizeCalendarState(
      '',
      household,
      new Date('2026-08-31T15:30:00Z'),
    )

    expect(state).toEqual({
      month: '2026-09',
      date: '2026-09-01',
      view: 'all',
      memberId: null,
    })
  })

  it('normalizes invalid month, date, view, and foreign member combinations', () => {
    const state = normalizeCalendarState(
      '?month=0000-01&view=member&date=2026-02-31&memberId=999',
      household,
      new Date('2026-08-28T03:00:00Z'),
    )

    expect(state).toEqual({
      month: '2026-08',
      date: '2026-08-28',
      view: 'all',
      memberId: null,
    })
  })

  it('keeps a valid actual Household member without ME or PARTNER aliases', () => {
    const state = normalizeCalendarState(
      '?month=2026-08&view=member&date=2026-08-12&memberId=101',
      household,
    )

    expect(state.view).toBe('member')
    expect(state.memberId).toBe(101)
    expect(calendarFilter(state)).toEqual({ scope: 'PERSONAL', ownerMemberId: 101 })
    expect(serializeCalendarState(state)).toBe(
      '?month=2026-08&view=member&date=2026-08-12&memberId=101',
    )
  })

  it('maps ALL and SHARED to their API filter contracts', () => {
    expect(calendarFilter({
      month: '2026-08',
      date: '2026-08-01',
      view: 'all',
      memberId: null,
    })).toEqual({ scope: 'ALL', ownerMemberId: null })
    expect(calendarFilter({
      month: '2026-08',
      date: '2026-08-01',
      view: 'shared',
      memberId: null,
    })).toEqual({ scope: 'SHARED', ownerMemberId: null })
  })

  it('clamps the selected day while moving between months', () => {
    const moved = moveCalendarMonth({
      month: '2026-01',
      date: '2026-01-31',
      view: 'member',
      memberId: 100,
    }, 1)

    expect(moved).toEqual({
      month: '2026-02',
      date: '2026-02-28',
      view: 'member',
      memberId: 100,
    })
  })

  it('builds a complete Sunday-first month grid', () => {
    const dates = calendarDates('2026-08')

    expect(dates).toHaveLength(42)
    expect(dates.slice(0, 6)).toEqual([null, null, null, null, null, null])
    expect(dates[6]).toBe('2026-08-01')
    expect(dates[36]).toBe('2026-08-31')
  })
})
