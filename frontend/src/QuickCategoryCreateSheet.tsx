import { type FormEvent, useEffect, useRef, useState } from 'react'
import {
  type Category,
  type CategoryGroup,
  LedgerApiError,
  createCategory,
} from './ledgerApi.ts'

function errorMessage(error: unknown) {
  if (error instanceof LedgerApiError) return error.message
  if (error instanceof Error && error.message) return error.message
  return 'Category를 추가하지 못했습니다.'
}

export function QuickCategoryCreateSheet({
  type,
  groups,
  categories,
  onCreated,
  onRequestClose,
}: {
  type: Category['type']
  groups: CategoryGroup[]
  categories: Category[]
  onCreated: (category: Category) => void
  onRequestClose: () => void
}) {
  const [name, setName] = useState('')
  const [groupId, setGroupId] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pendingRef = useRef(false)
  const nameRef = useRef<HTMLInputElement>(null)
  const matchingGroups = groups.filter((group) => group.type === type)

  useEffect(() => {
    nameRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pendingRef.current) {
        event.preventDefault()
        onRequestClose()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onRequestClose])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pendingRef.current) return
    pendingRef.current = true
    setPending(true)
    setError(null)
    try {
      const created = await createCategory({
        groupId: groupId ? Number(groupId) : null,
        name,
        type,
        iconKey: null,
        colorKey: null,
        sortOrder: categories.filter((category) => category.type === type).length,
      })
      onCreated(created)
      onRequestClose()
    } catch (submitError) {
      setError(errorMessage(submitError))
    } finally {
      pendingRef.current = false
      setPending(false)
    }
  }

  return (
    <div className="sheet-backdrop quick-category-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !pendingRef.current) onRequestClose()
    }}>
      <section
        className="bottom-sheet quick-category-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-category-title"
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-header">
          <div>
            <p className="section-kicker">Quick Entry</p>
            <h2 id="quick-category-title">
              {type === 'EXPENSE' ? '지출' : '수입'} 카테고리 추가
            </h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="카테고리 추가 닫기"
            disabled={pending}
            onClick={onRequestClose}
          >
            ×
          </button>
        </header>
        <form className="compact-form quick-category-form" onSubmit={submit}>
          <p className="field-hint">
            현재 {type === 'EXPENSE' ? '지출' : '수입'} 거래에 바로 선택됩니다.
          </p>
          <label>
            Category 이름
            <input
              ref={nameRef}
              required
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Group (선택)
            <select value={groupId} onChange={(event) => setGroupId(event.target.value)}>
              <option value="">그룹 없음</option>
              {matchingGroups.map((group) => (
                <option key={group.id} value={group.id}>{group.name}</option>
              ))}
            </select>
          </label>
          <div className="quick-category-actions">
            <button type="button" disabled={pending} onClick={onRequestClose}>취소</button>
            <button className="primary-button" type="submit" disabled={pending}>
              {pending ? '저장 중…' : '카테고리 저장'}
            </button>
          </div>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>
  )
}
