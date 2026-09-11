import { describe, expect, it } from 'vitest'
import {
  UI_VOCABULARY,
  householdRoleLabel,
  userFacingApiErrorMessage,
} from './uiVocabulary.ts'

describe('UI vocabulary', () => {
  it('keeps context-specific owner and payer labels distinct', () => {
    expect(UI_VOCABULARY.transactionOwner).toBe('귀속자')
    expect(UI_VOCABULARY.payer).toBe('결제자')
    expect(UI_VOCABULARY.accountOwner).toBe('소유자')
    expect(UI_VOCABULARY.accountOwnership).toBe('소유 기준')
  })

  it('maps internal Household roles to non-misleading Korean labels', () => {
    expect(householdRoleLabel('OWNER')).toBe('대표 구성원')
    expect(householdRoleLabel('MEMBER')).toBe('구성원')
  })

  it('localizes known API copy without hiding unknown server messages', () => {
    expect(userFacingApiErrorMessage(
      'TRANSACTION_INVALID_SCOPE',
      'Transaction scope와 owner 조합이 올바르지 않습니다.',
    )).toBe('거래 범위와 귀속자·결제자 설정이 올바르지 않습니다.')
    expect(userFacingApiErrorMessage('UNKNOWN', '서버 오류')).toBe('서버 오류')
    expect(userFacingApiErrorMessage(undefined, '일반 오류')).toBe('일반 오류')
  })
})
