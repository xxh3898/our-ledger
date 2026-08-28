import type { Account, LedgerTransaction } from './ledgerApi.ts'

export function isPrimaryAccountForType(
  type: LedgerTransaction['type'],
  account: Account,
) {
  if (account.archived || type === 'TRANSFER') return false
  if (type === 'INCOME') {
    return account.nature === 'ASSET' && account.type !== 'CREDIT_CARD'
  }
  return (account.nature === 'ASSET' && account.type !== 'CREDIT_CARD')
    || (account.type === 'CREDIT_CARD' && account.nature === 'LIABILITY')
}

export function entryByRole(
  transaction: LedgerTransaction,
  role: LedgerTransaction['entries'][number]['role'],
) {
  return transaction.entries.find((entry) => entry.role === role)
}
