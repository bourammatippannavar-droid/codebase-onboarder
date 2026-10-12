import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError } from './api/client'
import type { Overview, Repository } from './api/client'
import { useRepositories } from './api/hooks'
import {
  AnimatedNumber,
  Badge,
  Button,
  Card,
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  Kbd,
  Skeleton,
  ThemeToggle,
} from './components/ui'
import { OverviewContent, OverviewPage, RepositoriesPage } from './pages'
import { server } from './test/server'

const readyRepository = {
  id: 'repo-1',
  name: 'sample',
  path: 'examples/sample',
  status: 'ready',
  error: null,
  stats: { files: 2, symbols: 3 },
  created_at: '2026-10-11T00:00:00Z',
  finished_at: '2026-10-11T00:00:01Z',
} satisfies Repository

const overview = {
  files: 2,
  symbols: 3,
  loc: 48,
  cycle_count: 0,
  folders: [{ name: 'src', loc: 48, files: 2 }],
  call_confidence: { exact: 2, inferred: 1, unresolved: 1 },
  resolution_rate: 0.75,
  hotspots: [{
    file_id: 'file-1',
    path: 'src/main.py',
    imported_by: 1,
    blast_radius: 2,
    loc: 48,
    flags: ['central'],
  }],
  reading_order: [{ file_id: 'file-1', path: 'src/main.py', reason: 'entry point' }],
} satisfies Overview

function createClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderWithProviders(node: ReactNode) {
  return render(
    <QueryClientProvider client={createClient()}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('design system components', () => {
  it('shows confidence as readable text', () => {
    render(<ConfidenceBadge value="unresolved" />)
    expect(screen.getByText('unresolved')).toBeTruthy()
  })

  it('sets the full animated value when reduced motion is preferred', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }))
    render(<AnimatedNumber value={128} />)
    expect(screen.getByText('128')).toBeTruthy()
  })

  it('renders semantic surface, action, status, skeleton, and empty state', async () => {
    const user = userEvent.setup()
    const clicked = vi.fn()
    render(
      <>
        <Card aria-label="Summary"><h2>Summary card</h2></Card>
        <Button onClick={clicked}>Run</Button>
        <Badge tone="warn">central</Badge>
        <Skeleton lines={2} />
        <EmptyState title="Nothing here" description="No analysis is available." />
        <Kbd>Ctrl</Kbd>
      </>,
    )
    expect(screen.getByRole('region', { name: 'Summary' })).toBeTruthy()
    expect(screen.getByText('central')).toBeTruthy()
    expect(screen.getAllByLabelText('Loading')).toHaveLength(1)
    expect(screen.getByText('Nothing here')).toBeTruthy()
    expect(screen.getByText('Ctrl')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Run' }))
    expect(clicked).toHaveBeenCalledOnce()
  })

  it('exposes problem details and persists the selected theme', async () => {
    const user = userEvent.setup()
    const problem = new ApiError({
      type: 'about:blank',
      title: 'Analysis failed',
      status: 400,
      detail: 'Path rejected.',
      code: 'path_outside_root',
      request_id: 'req-2',
    }, 400)
    render(<><ErrorState error={problem} /><ThemeToggle /></>)
    expect(screen.getByRole('alert').textContent).toContain('path_outside_root: Path rejected.')
    await user.click(screen.getByRole('button', { name: /switch to light theme/i }))
    expect(localStorage.getItem('onboarder-theme')).toBe('light')
  })
})

describe('repositories', () => {
  afterEach(() => server.resetHandlers())

  it('validates the form and successfully adds a repository', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/repositories', () => HttpResponse.json([])),
      http.post('/api/v1/repositories', async ({ request }) => {
        const body = await request.json() as { name: string; path: string }
        expect(body).toEqual({ name: 'sample', path: 'C:\\work\\sample' })
        return HttpResponse.json({ ...readyRepository, status: 'pending' }, { status: 202 })
      }),
    )
    renderWithProviders(<RepositoriesPage />)
    await user.click(await screen.findByRole('button', { name: 'Add repository' }))
    expect(screen.getByRole('alert').textContent).toContain('Enter a repository name and path.')
    await user.type(await screen.findByLabelText('Name'), 'sample')
    await user.type(screen.getByLabelText('Local path'), 'C:\\work\\sample')
    await user.click(screen.getByRole('button', { name: 'Add repository' }))
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  })

  it('shows the stable server error code and detail', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/repositories', () => HttpResponse.json([])),
      http.post('/api/v1/repositories', () => HttpResponse.json({
        type: 'about:blank',
        title: 'Path outside root',
        status: 400,
        detail: 'Analysis path is outside the allowed root.',
        code: 'path_outside_root',
        request_id: 'test-request',
      }, { status: 400, headers: { 'Content-Type': 'application/problem+json' } })),
    )
    renderWithProviders(<RepositoriesPage />)
    await user.type(await screen.findByLabelText('Name'), 'bad')
    await user.type(screen.getByLabelText('Local path'), 'C:\\outside')
    await user.click(screen.getByRole('button', { name: 'Add repository' }))
    expect((await screen.findByRole('alert')).textContent).toContain(
      'path_outside_root: Analysis path is outside the allowed root.',
    )
  })

  it.each(['ready', 'failed'] as const)('stops polling when repository is %s', async (terminal) => {
    let calls = 0
    function Probe() {
      const query = useRepositories()
      return <output>{query.data?.[0]?.status ?? 'loading'}</output>
    }
    server.use(http.get('/api/v1/repositories', () => {
      calls += 1
      const status = calls === 1 ? 'pending' : terminal
      return HttpResponse.json([{ ...readyRepository, status }])
    }))
    renderWithProviders(<Probe />)
    await waitFor(() => expect(screen.getByText(terminal)).toBeTruthy(), { timeout: 3500 })
    const finalCalls = calls
    await new Promise((resolve) => window.setTimeout(resolve, 1700))
    expect(calls).toBe(finalCalls)
  })
})

describe('overview', () => {
  it('renders metrics, folder data, hotspots, and reading order', () => {
    render(<OverviewContent data={overview} onOpenFile={vi.fn()} />)
    expect(screen.getByText('Where the code lives')).toBeTruthy()
    expect(screen.getByText('src')).toBeTruthy()
    expect(screen.getAllByText('src/main.py')).toHaveLength(2)
    expect(screen.getByText('Dynamic calls are not guessed.')).toBeTruthy()
  })

  it('shows a friendly message while analysis is not ready', async () => {
    server.use(http.get('/api/v1/repositories/repo-1/overview', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Repository not ready',
      status: 409,
      detail: 'Repository analysis is not ready.',
      code: 'repository_not_ready',
      request_id: 'req-1',
    }, { status: 409, headers: { 'Content-Type': 'application/problem+json' } })))
    render(
      <QueryClientProvider client={createClient()}>
        <MemoryRouter initialEntries={['/repositories/repo-1/overview']}>
          <Routes>
            <Route path="/repositories/:repositoryId/overview" element={<OverviewPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Analysis is still running')).toBeTruthy()
  })
})

it('parses RFC 7807 into a typed API error', async () => {
  server.use(http.get('/api/v1/repositories', () => HttpResponse.json({
    type: 'about:blank',
    title: 'Not found',
    status: 404,
    detail: 'Repository was not found.',
    code: 'repository_not_found',
    request_id: 'request-123',
  }, { status: 404, headers: { 'Content-Type': 'application/problem+json' } })))
  await expect(api.repositories()).rejects.toMatchObject<ApiError>({
    name: 'ApiError',
    code: 'repository_not_found',
    message: 'Repository was not found.',
    requestId: 'request-123',
    status: 404,
  })
})
