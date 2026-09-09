import {
  type ComponentPropsWithRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
} from 'react'
import { amountInputCaret, formatAmountInput, parseAmountInput } from './amountInput.ts'

type AmountInputProps = Omit<ComponentPropsWithRef<'input'>,
  'type' | 'inputMode' | 'value' | 'defaultValue' | 'onChange' | 'onKeyDown' | 'onKeyUp'> & {
  value: string
  onValueChange: (value: string) => void
  allowNegative?: boolean
}

export function AmountInput({
  value,
  onValueChange,
  allowNegative = false,
  ref,
  min,
  max,
  ...props
}: AmountInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const selectionRef = useRef<[number, number] | null>(null)
  const deletionRef = useRef<string | null>(null)
  useImperativeHandle(ref, () => inputRef.current!, [])

  useLayoutEffect(() => {
    const input = inputRef.current
    if (!input) return
    let error = ''
    if (value === '-') error = '금액을 확인해 주세요.'
    else if (value !== '' && min !== undefined && Number(value) < Number(min)) {
      error = `${min}원 이상 입력해 주세요.`
    } else if (value !== '' && max !== undefined && Number(value) > Number(max)) {
      error = `${Number(max).toLocaleString('ko-KR')}원 이하 입력해 주세요.`
    }
    input.setCustomValidity(error)
    if (selectionRef.current && document.activeElement === input) {
      input.setSelectionRange(...selectionRef.current)
    }
    selectionRef.current = null
  })

  return <input
    {...props}
    ref={inputRef}
    type="text"
    inputMode="numeric"
    min={min}
    max={max}
    value={formatAmountInput(value)}
    onKeyDown={(event) => {
      deletionRef.current = event.key === 'Backspace'
        ? 'deleteContentBackward'
        : event.key === 'Delete' ? 'deleteContentForward' : null
    }}
    onKeyUp={() => { deletionRef.current = null }}
    onChange={(event) => {
      const input = event.currentTarget
      const previous = formatAmountInput(value)
      let draft = input.value
      let start = input.selectionStart ?? draft.length
      let end = input.selectionEnd ?? start
      const inputType = (event.nativeEvent as InputEvent).inputType || deletionRef.current
      deletionRef.current = null

      // A separator-only deletion must also remove the adjacent digit on mobile keyboards.
      if (start === end && previous.length === draft.length + 1
        && previous[start] === ',' && previous.replace(/,/g, '') === draft.replace(/,/g, '')
        && (inputType === 'deleteContentBackward' || inputType === 'deleteContentForward')) {
        const index = inputType === 'deleteContentBackward' ? start - 1 : start
        draft = draft.slice(0, index) + draft.slice(index + 1)
        start = inputType === 'deleteContentBackward' ? index : start
        end = start
      }

      const canonical = parseAmountInput(draft, allowNegative)
      if (canonical === null) {
        input.value = previous
        const restored = Math.max(0, start - Math.max(0, draft.length - previous.length))
        input.setSelectionRange(restored, restored)
        return
      }
      const display = formatAmountInput(canonical)
      const signLength = canonical.startsWith('-') ? 1 : 0
      const draftDigits = draft.replace(/,/g, '').slice(signLength)
      const removedZeros = draftDigits.length - (canonical.length - signLength)
      const position = (index: number) => {
        const signOffset = index > 0 ? signLength : 0
        const digitsBefore = draft.slice(0, index).replace(/,/g, '').length - signOffset
        return amountInputCaret(display, signOffset + Math.max(0, digitsBefore - removedZeros))
      }
      selectionRef.current = [position(start), position(end)]
      input.value = display
      input.setSelectionRange(...selectionRef.current)
      onValueChange(canonical)
    }}
  />
}
