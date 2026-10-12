import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { describe, expect, it, vi } from 'vitest'

import { CommandPalette } from './CommandPalette'
import { server } from '../test/server'

function CurrentLocation() {
  const location = useLocation()
  return <output aria-label="Current URL">{location.pathname}{location.search}</output>
}

function PaletteRoute({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(true)
  return open
    ? <CommandPalette repositoryId="repo-1" onClose={() => { onClose(); setOpen(false) }} />
    : <p>Palette closed</p>
}

function renderPalette(onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/repositories/repo-1']}>
        <CurrentLocation />
        <Routes>
          <Route path="/repositories/:repositoryId" element={<PaletteRoute onClose={onClose} />} />
          <Route path="/repositories/:repositoryId/explorer" element={<p>Explorer route</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...view, onClose }
}

const fileResult = {
  kind: 'file',
  file_id: 'file-1',
  path: 'src/main.py',
  name: 'main.py',
  qualified_name: null,
  symbol_id: null,
  symbol_kind: null,
}

describe('command palette', () => {
  it('debounces search, opens a result with Enter, and closes on Escape', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories/repo-1/search', ({ request }) => {
      expect(new URL(request.url).searchParams.get('q')).toBe('main')
      return HttpResponse.json({ items: [fileResult], total: 1 })
    }))
    const { onClose } = renderPalette()
    const input = screen.getByRole('textbox', { name: 'Search files and symbols' })
    expect(document.activeElement).toBe(input)
    await user.type(input, 'main')
    await screen.findByRole('option', { name: /main\.py/ })
    await user.keyboard('{ArrowDown}{Enter}')
    await waitFor(() => expect(screen.getByLabelText('Current URL').textContent).toContain('/explorer?file=file-1'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('traps Tab within the modal and treats wildcard query characters literally', async () => {
    const user = userEvent.setup()
    const requestedQueries: string[] = []
    server.use(http.get('/api/v1/repositories/repo-1/search', ({ request }) => {
      requestedQueries.push(new URL(request.url).searchParams.get('q') ?? '')
      return HttpResponse.json({ items: [], total: 0 })
    }))
    renderPalette()
    const input = screen.getByRole('textbox', { name: 'Search files and symbols' })
    await user.type(input, '%%')
    await screen.findByText('No matching files or symbols.')
    await waitFor(() => expect(requestedQueries).toContain('%%'))
    const methodChip = screen.getByRole('button', { name: 'method' })
    methodChip.focus()
    await user.tab()
    expect(document.activeElement).toBe(input)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows problem+json error code and detail', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories/repo-1/search', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Search failed',
      status: 503,
      detail: 'Search is unavailable.',
      code: 'search_unavailable',
      request_id: 'search-test',
    }, { status: 503, headers: { 'Content-Type': 'application/problem+json' } })))
    renderPalette()
    await user.type(screen.getByRole('textbox', { name: 'Search files and symbols' }), 'runner')
    expect(await screen.findByText(/search_unavailable: Search is unavailable\./)).toBeTruthy()
  })
})
