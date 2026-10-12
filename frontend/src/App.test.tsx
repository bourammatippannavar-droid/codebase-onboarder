import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import App from './App'
import { server } from './test/server'

describe('application search shortcut', () => {
  it('opens the command palette with Ctrl+K and restores focus when it closes', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories', () => HttpResponse.json([{
      id: 'repo-1',
      name: 'sample',
      path: 'examples/sample',
      status: 'ready',
      error: null,
      stats: { files: 1, symbols: 1 },
      created_at: '2026-10-11T00:00:00Z',
      finished_at: '2026-10-11T00:00:01Z',
    }])))
    server.use(http.get('/api/v1/repositories/repo-1/overview', () => HttpResponse.json({
      files: 1,
      symbols: 1,
      loc: 8,
      cycle_count: 0,
      folders: [],
      call_confidence: { exact: 0, inferred: 0, unresolved: 0 },
      resolution_rate: null,
      hotspots: [],
      reading_order: [],
    })))
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/repositories/repo-1/overview']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const trigger = await screen.findByRole('button', { name: 'Search repository' })
    await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false))
    fireEvent.keyDown(document.body, { key: 'k', ctrlKey: true })
    expect(await screen.findByRole('dialog', { name: 'Search this repository' })).toBeTruthy()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
})
