import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from '../App'

// Home page fetches reports only after cancer selection; stub fetch for safety.
vi.stubGlobal(
  'fetch',
  vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => [],
      text: async () => '[]',
    }),
  ),
)

describe('App smoke', () => {
  it('renders PathExplain home without crashing', () => {
    render(<App />)
    expect(screen.getAllByText(/PathExplain/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Research demo, not for clinical use/i)).toBeInTheDocument()
    expect(screen.getByText(/Pathology reports, explained in plain language/i)).toBeInTheDocument()
  })
})
