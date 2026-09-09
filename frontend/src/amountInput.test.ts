import { describe, expect, it } from 'vitest'
import { amountInputCaret, formatAmountInput, parseAmountInput } from './amountInput.ts'

describe('amount input strings', () => {
  it.each([
    ['', '', ''],
    ['0', '0', '0'],
    ['1', '1', '1'],
    ['1000', '1000', '1,000'],
    ['1234567', '1234567', '1,234,567'],
    ['001000', '1000', '1,000'],
    ['1,000', '1000', '1,000'],
    [',234', '234', '234'],
    ['9223372036854775807', '9223372036854775807', '9,223,372,036,854,775,807'],
  ])('keeps %s canonical and formats its digits without rounding', (input, canonical, display) => {
    expect(parseAmountInput(input)).toBe(canonical)
    expect(formatAmountInput(canonical)).toBe(display)
  })

  it.each(['1a000', '₩1000', '1.5', '1e3', '+1000', ' 1000 ', ',', '-1000'])(
    'rejects the complete unsupported edit %s instead of silently changing its amount', (value) => {
      expect(parseAmountInput(value)).toBeNull()
    },
  )

  it('preserves signed opening balances and the temporary minus draft', () => {
    expect(parseAmountInput('-', true)).toBe('-')
    expect(parseAmountInput('-001000', true)).toBe('-1000')
    expect(formatAmountInput('-1000')).toBe('-1,000')
    expect(parseAmountInput('-0', true)).toBe('-0')
  })

  it('maps canonical offsets around separators, including signed amounts', () => {
    expect(amountInputCaret('1,234,567', 0)).toBe(0)
    expect(amountInputCaret('1,234,567', 2)).toBe(3)
    expect(amountInputCaret('-1,000', 2)).toBe(2)
    expect(amountInputCaret('1,234', 20)).toBe(5)
  })
})
