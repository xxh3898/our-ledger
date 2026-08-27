import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('App', () => {
  it('renders the loading state while the current user request is pending', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))

    render(<App />)

    expect(screen.getByRole('status')).toHaveTextContent(
      '현재 사용자와 Household를 확인하고 있습니다.',
    )
  })

  it('renders the current user household and role on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          userId: 1,
          email: 'owner@example.test',
          displayName: 'Owner',
          householdId: 10,
          householdName: '테스트 Household',
          role: 'OWNER',
        }),
      ),
    )

    render(<App />)

    expect(await screen.findByRole('heading', { level: 2, name: 'Owner' })).toBeInTheDocument()
    expect(screen.getByText('owner@example.test')).toBeInTheDocument()
    expect(screen.getByText('테스트 Household')).toBeInTheDocument()
    expect(screen.getByText('OWNER')).toBeInTheDocument()
  })

  it('renders an authentication message on 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, 401)))

    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('인증이 필요합니다.')
    expect(screen.getByText(/Cloudflare Access 인증/)).toBeInTheDocument()
  })

  it('renders an unregistered user message on 403', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ code: 'USER_NOT_REGISTERED' }, 403)),
    )

    render(<App />)

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('등록된 사용자가 아닙니다.'),
    )
    expect(screen.getByText(/내부 User와 Household membership/)).toBeInTheDocument()
  })
})
