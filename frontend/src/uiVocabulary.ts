export type HouseholdRole = 'OWNER' | 'MEMBER'

export const UI_VOCABULARY = {
  transactionOwner: '귀속자',
  payer: '결제자',
  accountOwner: '소유자',
  accountOwnership: '소유 기준',
} as const

const HOUSEHOLD_ROLE_LABELS = {
  OWNER: '대표 구성원',
  MEMBER: '구성원',
} satisfies Record<HouseholdRole, string>

const UI_API_ERROR_MESSAGES: Record<string, string> = {
  TRANSACTION_INVALID_SCOPE:
    `거래 범위와 ${UI_VOCABULARY.transactionOwner}·${UI_VOCABULARY.payer} 설정이 올바르지 않습니다.`,
}

export function householdRoleLabel(role: HouseholdRole) {
  return HOUSEHOLD_ROLE_LABELS[role]
}

export function userFacingApiErrorMessage(code: string | undefined, fallback: string) {
  return code ? UI_API_ERROR_MESSAGES[code] ?? fallback : fallback
}
