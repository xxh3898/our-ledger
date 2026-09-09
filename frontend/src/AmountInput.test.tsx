import { type ComponentProps, useRef, useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AmountInput } from './AmountInput.tsx'

afterEach(cleanup)

function Editor({ initial = '', ...props }: Omit<ComponentProps<typeof AmountInput>,
  'value' | 'onValueChange'> & { initial?: string }) {
  const [value, setValue] = useState(initial)
  return <>
    <AmountInput aria-label="금액" {...props} value={value} onValueChange={setValue} />
    <output data-testid="canonical">{value}</output>
  </>
}

function input() {
  return screen.getByRole('textbox', { name: '금액' }) as HTMLInputElement
}

function edit(value: string, caret = value.length, inputType = 'insertText') {
  input().focus()
  fireEvent.input(input(), { target: { value, selectionStart: caret, selectionEnd: caret }, inputType })
}

describe('AmountInput', () => {
  it('formats immediately while retaining an empty or numeric canonical draft', () => {
    render(<Editor required min="1" />)
    expect(input()).toHaveValue('')
    expect(input()).toBeInvalid()
    expect(input()).toHaveAttribute('inputmode', 'numeric')
    edit('1000')
    expect(input()).toHaveValue('1,000')
    expect(screen.getByTestId('canonical')).toHaveTextContent('1000')
    expect(input().selectionStart).toBe(5)
    edit('1,0000')
    expect(input()).toHaveValue('10,000')
    expect(input().selectionStart).toBe(6)
    edit('1234567')
    expect(input()).toHaveValue('1,234,567')
    edit('')
    expect(input()).toHaveValue('')
    expect(screen.getByTestId('canonical')).toBeEmptyDOMElement()
  })

  it('preserves middle insertion and ordinary backspace caret positions', () => {
    render(<Editor initial="1234567" />)
    edit('1,2934,567', 4)
    expect(input()).toHaveValue('12,934,567')
    expect(input().selectionStart).toBe(4)
    edit('12,34,567', 3, 'deleteContentBackward')
    expect(input()).toHaveValue('1,234,567')
    expect(input().selectionStart).toBe(3)
  })

  it('allows deleting the first digit before a separator', () => {
    render(<Editor initial="1234" />)
    edit(',234', 0, 'deleteContentBackward')
    expect(input()).toHaveValue('234')
    expect(input().selectionStart).toBe(0)
  })

  it.each([
    ['deleteContentBackward', '234', 0],
    ['deleteContentForward', '134', 1],
  ] as const)('deletes a digit when %s removes only a comma on a mobile input event', (inputType, display, caret) => {
    render(<Editor initial="1234" />)
    edit('1234', 1, inputType)
    expect(input()).toHaveValue(display)
    expect(input().selectionStart).toBe(caret)
  })

  it('uses keyboard deletion direction when a browser omits inputType', () => {
    render(<Editor initial="1234" />)
    input().focus()
    input().setSelectionRange(2, 2)
    fireEvent.keyDown(input(), { key: 'Backspace' })
    fireEvent.change(input(), { target: { value: '1234', selectionStart: 1, selectionEnd: 1 } })
    expect(input()).toHaveValue('234')
    expect(input().selectionStart).toBe(0)
  })

  it('supports selection replacement, grouped paste, zero replacement and leading-zero normalization', () => {
    render(<Editor initial="1234" />)
    input().setSelectionRange(0, 5)
    edit('500000')
    expect(input()).toHaveValue('500,000')
    fireEvent.paste(input(), { clipboardData: { getData: () => '1,234,567' } })
    edit('1,234,567', 9, 'insertFromPaste')
    expect(input()).toHaveValue('1,234,567')
    expect(screen.getByTestId('canonical')).toHaveTextContent('1234567')
    edit('0')
    expect(input()).toHaveValue('0')
    edit('001000')
    expect(input()).toHaveValue('1,000')
    expect(input().selectionStart).toBe(5)
  })

  it('rejects unsupported edits intact, including paste, without stripping meaningful characters', () => {
    render(<Editor initial="1000" />)
    edit('1,00x0', 5)
    expect(input()).toHaveValue('1,000')
    edit('12.50', 5, 'insertFromPaste')
    expect(input()).toHaveValue('1,000')
    expect(screen.getByTestId('canonical')).toHaveTextContent('1000')
  })

  it('preserves required, zero, and the current Refund maximum boundary without clamping', () => {
    render(<Editor required min="1" max={30000} />)
    edit('0')
    expect(input()).toBeInvalid()
    edit('30000')
    expect(input()).toHaveValue('30,000')
    expect(input()).toBeValid()
    edit('30001')
    expect(input()).toHaveValue('30,001')
    expect(input()).toBeInvalid()
    expect(screen.getByTestId('canonical')).toHaveTextContent('30001')
  })

  it('allows a zero Budget but keeps required empty invalid', () => {
    render(<Editor required min="0" />)
    edit('0')
    expect(input()).toBeValid()
    edit('')
    expect(input()).toBeInvalid()
  })

  it('keeps optional signed opening balances, the minus draft, and long digit strings', () => {
    render(<Editor allowNegative initial="0" />)
    edit('')
    expect(input()).toBeValid()
    edit('-')
    expect(input()).toHaveValue('-')
    expect(input()).toBeInvalid()
    edit('-1000')
    expect(input()).toHaveValue('-1,000')
    expect(input()).toBeValid()
    edit('9223372036854775807')
    expect(input()).toHaveValue('9,223,372,036,854,775,807')
    expect(screen.getByTestId('canonical')).toHaveTextContent('9223372036854775807')
  })

  it('forwards focus and remains stable when the parent supplies a new canonical value', () => {
    function Parent() {
      const ref = useRef<HTMLInputElement>(null)
      return <>
        <AmountInput ref={ref} aria-label="금액" value="1234" onValueChange={vi.fn()} />
        <button onClick={() => ref.current?.focus()}>focus</button>
      </>
    }
    render(<Parent />)
    fireEvent.click(screen.getByRole('button', { name: 'focus' }))
    expect(input()).toHaveFocus()
    expect(input()).toHaveValue('1,234')
  })
})
