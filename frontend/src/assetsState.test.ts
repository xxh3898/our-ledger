import { describe, expect, it } from 'vitest'
import type { CurrentHousehold } from './ledgerApi.ts'
import {
  isAssetsScreen,
  normalizeAssetsState,
  serializeAssetsState,
} from './assetsState.ts'

const household: CurrentHousehold = {
  householdId: 10,
  name: '우리 집',
  baseCurrency: 'KRW',
  timezone: 'Asia/Seoul',
  members: [
    { memberId: 100, userId: 1, displayName: 'Owner', role: 'OWNER' },
    { memberId: 101, userId: 2, displayName: 'Member', role: 'MEMBER' },
  ],
}

describe('assetsState', () => {
  it('normalizes direct all, actual member, and shared views', () => {
    expect(normalizeAssetsState('?screen=assets&view=all', household))
      .toEqual({ view: 'all', memberId: null })
    expect(normalizeAssetsState('?screen=assets&view=personal&memberId=101', household))
      .toEqual({ view: 'personal', memberId: 101 })
    expect(normalizeAssetsState('?screen=assets&view=shared', household))
      .toEqual({ view: 'shared', memberId: null })
  })

  it('fails closed to all when member or view is invalid', () => {
    expect(normalizeAssetsState('?screen=assets&view=personal&memberId=999', household))
      .toEqual({ view: 'all', memberId: null })
    expect(normalizeAssetsState('?screen=assets&view=personal&memberId=1.5', household))
      .toEqual({ view: 'all', memberId: null })
    expect(normalizeAssetsState('?screen=assets&view=unknown&memberId=100', household))
      .toEqual({ view: 'all', memberId: null })
    expect(normalizeAssetsState('?screen=calendar&view=shared', household))
      .toEqual({ view: 'all', memberId: null })
  })

  it('serializes canonical URLs without unrelated parameters', () => {
    expect(serializeAssetsState({ view: 'all', memberId: null }))
      .toBe('?screen=assets&view=all')
    expect(serializeAssetsState({ view: 'personal', memberId: 100 }))
      .toBe('?screen=assets&view=personal&memberId=100')
    expect(serializeAssetsState({ view: 'shared', memberId: null }))
      .toBe('?screen=assets&view=shared')
    expect(isAssetsScreen('?screen=assets&view=all')).toBe(true)
    expect(isAssetsScreen('?screen=statistics')).toBe(false)
  })
})
