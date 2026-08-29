import type { CurrentHousehold } from './ledgerApi.ts'

export type AssetsNavigationState =
  | { view: 'all'; memberId: null }
  | { view: 'personal'; memberId: number }
  | { view: 'shared'; memberId: null }

export function isAssetsScreen(search: string) {
  return new URLSearchParams(search).get('screen') === 'assets'
}

export function normalizeAssetsState(
  search: string,
  household: CurrentHousehold,
): AssetsNavigationState {
  const parameters = new URLSearchParams(search)
  if (parameters.get('screen') !== 'assets') {
    return { view: 'all', memberId: null }
  }
  if (parameters.get('view') === 'shared') {
    return { view: 'shared', memberId: null }
  }
  if (parameters.get('view') === 'personal') {
    const rawMemberId = parameters.get('memberId') ?? ''
    if (/^[1-9][0-9]*$/.test(rawMemberId)) {
      const memberId = Number(rawMemberId)
      if (household.members.some((member) => member.memberId === memberId)) {
        return { view: 'personal', memberId }
      }
    }
  }
  return { view: 'all', memberId: null }
}

export function serializeAssetsState(state: AssetsNavigationState) {
  const parameters = new URLSearchParams({ screen: 'assets', view: state.view })
  if (state.view === 'personal') {
    parameters.set('memberId', state.memberId.toString())
  }
  return `?${parameters}`
}
