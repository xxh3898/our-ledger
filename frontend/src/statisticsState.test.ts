import { describe, expect, it } from 'vitest'
import type { CurrentHousehold } from './ledgerApi.ts'
import {
  normalizeStatisticsState,
  presetRange,
  serializeStatisticsState,
  statisticsFilter,
  withStatisticsPreset,
} from './statisticsState.ts'

const household: CurrentHousehold = {
  householdId: 10,
  name: '우리집',
  baseCurrency: 'KRW',
  timezone: 'Asia/Seoul',
  members: [
    { memberId: 100, userId: 1, displayName: 'Owner', role: 'OWNER' },
    { memberId: 101, userId: 2, displayName: 'Member', role: 'MEMBER' },
  ],
}
const now = new Date('2026-08-28T03:00:00Z')

describe('statisticsState', () => {
  it('defaults to this month and all with the previous calendar month comparison', () => {
    expect(normalizeStatisticsState('', household, now)).toEqual({
      preset: 'this-month',
      from: '2026-08-01',
      to: '2026-08-31',
      compareFrom: '2026-07-01',
      compareTo: '2026-07-31',
      view: 'all',
      memberId: null,
    })
  })

  it('derives adjacent calendar ranges for every preset', () => {
    expect(presetRange('last-month', household.timezone, now)).toEqual({
      from: '2026-07-01',
      to: '2026-07-31',
      compareFrom: '2026-06-01',
      compareTo: '2026-06-30',
    })
    expect(presetRange('recent-3-months', household.timezone, now)).toEqual({
      from: '2026-06-01',
      to: '2026-08-31',
      compareFrom: '2026-03-01',
      compareTo: '2026-05-31',
    })
    expect(presetRange('recent-6-months', household.timezone, now).from).toBe('2026-03-01')
    expect(presetRange('year', household.timezone, now).from).toBe('2025-09-01')
  })

  it('keeps valid custom member state and normalizes invalid dates or foreign members', () => {
    const valid = normalizeStatisticsState(
      '?screen=statistics&preset=custom&from=2026-06-15&to=2026-08-20&view=member&memberId=101',
      household,
      now,
    )
    expect(valid).toEqual({
      preset: 'custom',
      from: '2026-06-15',
      to: '2026-08-20',
      compareFrom: '2026-04-09',
      compareTo: '2026-06-14',
      view: 'member',
      memberId: 101,
    })
    expect(statisticsFilter(valid)).toEqual({ scope: 'PERSONAL', ownerMemberId: 101 })

    const normalized = normalizeStatisticsState(
      '?screen=statistics&preset=custom&from=2026-02-30&to=2026-01-01&view=member&memberId=999',
      household,
      now,
    )
    expect(normalized.preset).toBe('this-month')
    expect(normalized.view).toBe('all')
    expect(normalized.memberId).toBeNull()
  })

  it('serializes canonical state and rejects an invalid custom update', () => {
    const state = normalizeStatisticsState(
      '?screen=statistics&preset=this-month&view=shared', household, now,
    )
    expect(serializeStatisticsState(state))
      .toBe('?screen=statistics&preset=this-month&view=shared')
    expect(withStatisticsPreset(
      state,
      'custom',
      household,
      { from: '2026-08-20', to: '2026-08-01' },
    )).toBeNull()
  })
})
