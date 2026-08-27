import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App.tsx'

describe('App', () => {
  it('renders the Foundation status', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: '우리의 장부' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Foundation 준비 완료')
    expect(screen.getByText('Spring Boot 4.1')).toBeInTheDocument()
    expect(screen.getByText('React 19.2')).toBeInTheDocument()
  })
})
