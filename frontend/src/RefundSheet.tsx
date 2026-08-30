import { type FormEvent, useEffect, useRef, useState } from 'react'
import { noonInTimeZone, todayInTimeZone } from './dateTime.ts'
import {
  type CurrentHousehold,
  type LedgerTransaction,
  type RefundSummary,
  LedgerApiError,
  createRefund,
  loadRefundSummary,
} from './ledgerApi.ts'
import { entryByRole } from './transactionUtils.ts'

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return '환불을 기록하지 못했습니다.'
}

function formatWon(amount: number) {
  return `${amount.toLocaleString('ko-KR')}원`
}

export function RefundSheet({
  household,
  original,
  initialSummary,
  onRequestClose,
  onSaved,
}: {
  household: CurrentHousehold
  original: LedgerTransaction
  initialSummary: RefundSummary
  onRequestClose: () => void
  onSaved: () => void
}) {
  const [summary, setSummary] = useState(initialSummary)
  const [amount, setAmount] = useState('')
  const [occurredOn, setOccurredOn] = useState(
    todayInTimeZone(household.timezone),
  )
  const [memo, setMemo] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const amountRef = useRef<HTMLInputElement>(null)
  const account = entryByRole(original, 'PRIMARY')?.account

  useEffect(() => {
    amountRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) {
        event.preventDefault()
        onRequestClose()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onRequestClose, pending])

  async function refreshSummary() {
    try {
      setSummary(await loadRefundSummary(original.id))
    } catch {
      // The server error remains the primary actionable feedback.
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setPending(true)
    setError(null)
    setSuccess(null)
    try {
      const refundAmount = Number(amount)
      if (!amount || refundAmount <= 0) {
        throw new Error('환불 금액을 확인해 주세요.')
      }
      if (refundAmount > summary.remainingRefundableAmount) {
        throw new Error(
          `환불 가능 금액은 ${formatWon(summary.remainingRefundableAmount)}입니다.`,
        )
      }
      await createRefund(original.id, {
        amount: refundAmount,
        occurredAt: noonInTimeZone(occurredOn, household.timezone),
        memo: memo.trim() || null,
      })
      setSuccess('환불을 기록했어요 🐾')
      onSaved()
      await new Promise((resolve) => window.setTimeout(resolve, 500))
      onRequestClose()
    } catch (submitError) {
      setError(errorMessage(submitError))
      if (
        submitError instanceof LedgerApiError
        && submitError.code === 'TRANSACTION_REFUND_EXCEEDS_ORIGINAL'
      ) {
        await refreshSummary()
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pending) onRequestClose()
    }}>
      <section
        className="bottom-sheet refund-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="refund-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Refund</p>
            <h2 id="refund-title">환불 처리</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="환불 처리 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <section className="refund-context" aria-label="원 거래 정보">
          <strong>
            {original.category?.name ?? '지출'} · {formatWon(original.amount)}
          </strong>
          <span>{account?.name ?? 'Account'}</span>
          <dl>
            <div>
              <dt>이미 환불</dt>
              <dd>{formatWon(summary.refundedAmount)}</dd>
            </div>
            <div>
              <dt>환불 가능</dt>
              <dd>{formatWon(summary.remainingRefundableAmount)}</dd>
            </div>
          </dl>
        </section>
        <form className="entry-form" noValidate onSubmit={submit}>
          <label className="amount-field">
            환불 금액
            <span>
              <input
                ref={amountRef}
                aria-label="환불 금액"
                required
                autoFocus
                min="1"
                max={summary.remainingRefundableAmount}
                inputMode="numeric"
                type="number"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              /> 원
            </span>
          </label>
          <label>
            날짜
            <input
              required
              type="date"
              value={occurredOn}
              onChange={(event) => setOccurredOn(event.target.value)}
            />
          </label>
          <label className="memo-field">
            메모 (선택)
            <input value={memo} onChange={(event) => setMemo(event.target.value)} />
          </label>
          <button className="primary-button sheet-submit" type="submit" disabled={pending}>
            {pending
              ? '환불 기록 중…'
              : amount && Number(amount) > 0
                ? `${formatWon(Number(amount))} 환불 기록`
                : '환불 기록'}
          </button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
        {success && <p className="save-success" role="status">{success}</p>}
      </section>
    </div>
  )
}
