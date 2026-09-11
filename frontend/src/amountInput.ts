/** A canonical draft stays a string so empty and zero remain distinct. */
export function parseAmountInput(display: string, allowNegative = false): string | null {
  if (display === '') return ''
  if (allowNegative && display === '-') return '-'
  const canonical = display.replace(/,/g, '')
  const pattern = allowNegative ? /^-?\d+$/ : /^\d+$/
  if (!pattern.test(canonical)) return null
  return canonical.replace(/^(-?)0+(?=\d)/, '$1')
}

/** Format digits directly, without a floating-point round trip. */
export function formatAmountInput(canonical: string): string {
  return canonical.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

export function amountInputCaret(display: string, offset: number): number {
  if (offset <= 0) return 0
  let remaining = offset
  for (let index = 0; index < display.length; index += 1) {
    if (display[index] !== ',') remaining -= 1
    if (remaining === 0) return index + 1
  }
  return display.length
}
