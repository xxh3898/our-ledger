import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  currentBudgetMonth,
  isBudgetScreen,
  moveBudgetMonth,
  normalizeBudgetMonth,
  serializeBudgetState,
} from './budgetState.ts'

describe('budgetState', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-08-31T15:30:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('uses the Household timezone month when the URL month is missing or invalid', () => {
    expect(currentBudgetMonth('Asia/Seoul')).toBe('2026-09')
    expect(normalizeBudgetMonth('?screen=budget', 'Asia/Seoul')).toBe('2026-09')
    expect(normalizeBudgetMonth('?screen=budget&month=2026-13', 'Asia/Seoul')).toBe('2026-09')
    expect(normalizeBudgetMonth('?screen=budget&month=2026-08', 'Asia/Seoul')).toBe('2026-08')
  })

  it('serializes the Budget destination and moves across year boundaries', () => {
    expect(isBudgetScreen('?screen=budget&month=2026-08')).toBe(true)
    expect(isBudgetScreen('?month=2026-08')).toBe(false)
    expect(serializeBudgetState('2026-08')).toBe('?screen=budget&month=2026-08')
    expect(moveBudgetMonth('2026-01', -1)).toBe('2025-12')
    expect(moveBudgetMonth('2026-12', 1)).toBe('2027-01')
  })
})
