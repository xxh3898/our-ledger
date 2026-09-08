import { describe, expect, it } from 'vitest'
import { todayInTimeZone } from './dateTime.ts'

describe('todayInTimeZone', () => {
  it('changes the Household date at its timezone boundary instead of the UTC boundary', () => {
    const beforeSeoulMidnight = new Date('2026-09-02T14:59:59Z')
    const afterSeoulMidnight = new Date('2026-09-02T15:00:00Z')

    expect(todayInTimeZone('Asia/Seoul', beforeSeoulMidnight)).toBe('2026-09-02')
    expect(todayInTimeZone('Asia/Seoul', afterSeoulMidnight)).toBe('2026-09-03')
    expect(todayInTimeZone('UTC', afterSeoulMidnight)).toBe('2026-09-02')
  })
})
