import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { ModuleGraph } from '../api/client'
import { server } from '../test/server'
import { GraphPage } from './GraphPage'

const moduleGraph = {
  nodes: [
    {
      id: 'folder-src',
      kind: 'folder',
      name: 'src',
      path: 'src',
      file_count: 1,
      loc: 24,
      in_cycle: false,
    },
    {
      id: 'file-main',
      kind: 'file',
      file_id: 'file-main',
      name: 'main.py',
      path: 'main.py',
      loc: 24,
      imported_by: 0,
      is_entry_point: true,
      in_cycle: false,
      central: false,
    },
  ],
  edges: [
    { source: 'folder-src', target: 'file-main', count: 2, in_cycle: true },
  ],
  truncated: true,
  total_nodes: 174,
} satisfies ModuleGraph

function LocationOutput() {
  const location = useLocation()
  return <output aria-label="Current location">{location.pathname}{location.search}</output>
}

function BrowserBackButton() {
  const navigate = useNavigate()
  return <button type="button" onClick={() => navigate(-1)}>Browser back</button>
}

function renderGraph(initialEntry = '/repositories/repo-1/graph') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocationOutput />
        <BrowserBackButton />
        <Routes>
          <Route path="/repositories/:repositoryId/graph" element={<GraphPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function graphResponse(graph: ModuleGraph = moduleGraph) {
  return HttpResponse.json(graph)
}

describe('interactive dependency graph', () => {
  it('shows the truncated graph and selected node details', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse()))
    renderGraph('/repositories/repo-1/graph?view=list')

    expect(await screen.findByText('Showing the largest 150 of 174 items')).toBeTruthy()
    await user.click(await screen.findByRole('row', { name: /main\.py file/i }))
    expect(await screen.findByRole('complementary', { name: 'Selected node details' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'main.py' })).toBeTruthy()
  })

  it('drills down, restores the previous URL with Back, and follows breadcrumbs', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', ({ request }) => {
      const path = new URL(request.url).searchParams.get('path_prefix')
      return graphResponse(path === 'src' ? { ...moduleGraph, nodes: [], edges: [], total_nodes: 0 } : moduleGraph)
    }))
    renderGraph('/repositories/repo-1/graph?view=list')

    const sourceRow = await screen.findByRole('row', { name: /src folder 1 24/i })
    await user.dblClick(sourceRow)
    await waitFor(() => expect(screen.getByLabelText('Current location').textContent).toContain('?view=list&path=src'))
    expect(await screen.findByText('No modules at this level')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Browser back' }))
    await screen.findByRole('table', { name: 'Dependency graph nodes' })
    expect(screen.getByLabelText('Current location').textContent).not.toContain('path=src')

    await user.dblClick(screen.getByRole('row', { name: /src folder 1 24/i }))
    expect(await screen.findByText('No modules at this level')).toBeTruthy()
    await user.click(screen.getByRole('link', { name: 'All modules' }))
    await screen.findByRole('table', { name: 'Dependency graph nodes' })
    expect(screen.getByLabelText('Current location').textContent).not.toContain('path=src')
  })

  it('filters graph nodes and lists the same graph edges accessibly', async () => {
    const user = userEvent.setup()
    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse()))
    renderGraph('/repositories/repo-1/graph?view=list')

    const filter = await screen.findByRole('textbox', { name: 'Filter graph nodes' })
    await user.type(filter, 'missing')
    const nodesTable = screen.getByRole('table', { name: 'Dependency graph nodes' })
    expect(within(nodesTable).getAllByRole('row')).toHaveLength(3)
    expect(within(nodesTable).getByRole('row', { name: /src folder/i }).className).toContain('graph-list-dimmed')
    expect(screen.getByRole('table', { name: 'Dependency graph edges' }).textContent).toContain('2')

    await user.clear(filter)
    await user.click(screen.getByRole('button', { name: 'Graph view' }))
    expect(await screen.findByLabelText('Interactive module dependency graph')).toBeTruthy()
  })

  it('loads and clears blast-radius highlighting, reporting request failures', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse()),
      http.get('/api/v1/repositories/repo-1/files/file-main/dependents', () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
    )
    renderGraph('/repositories/repo-1/graph?view=list')
    await user.click(await screen.findByRole('row', { name: /main\.py file/i }))
    await user.click(screen.getByRole('button', { name: 'Show blast radius' }))
    expect(await screen.findByText('0 files affected')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Clear blast radius highlight' }))
    expect(screen.queryByText('0 files affected')).toBeNull()
  })

  it('shows a loading state while blast-radius results are pending', async () => {
    const user = userEvent.setup()
    let releaseResponse: (() => void) | undefined
    const responsePending = new Promise<void>((resolve) => {
      releaseResponse = resolve
    })
    server.use(
      http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse()),
      http.get('/api/v1/repositories/repo-1/files/file-main/dependents', async () => {
        await responsePending
        return HttpResponse.json({ items: [], total: 0 })
      }),
    )
    renderGraph('/repositories/repo-1/graph?view=list')
    await user.click(await screen.findByRole('row', { name: /main\.py file/i }))
    await user.click(screen.getByRole('button', { name: 'Show blast radius' }))
    const loadingButton = await screen.findByRole('button', { name: 'Loading impact…' })
    expect(loadingButton.hasAttribute('disabled')).toBe(true)
    releaseResponse?.()
    expect(await screen.findByText('0 files affected')).toBeTruthy()
  })

  it('shows the API problem when blast-radius loading fails without changing the graph', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse()),
      http.get('/api/v1/repositories/repo-1/files/file-main/dependents', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Could not load dependents',
      status: 500,
      detail: 'The graph could not be loaded.',
      code: 'graph_unavailable',
      request_id: 'graph-test',
      }, { status: 500, headers: { 'Content-Type': 'application/problem+json' } })),
    )
    renderGraph('/repositories/repo-1/graph?view=list')
    await user.click(await screen.findByRole('row', { name: /main\.py file/i }))
    await user.click(screen.getByRole('button', { name: 'Show blast radius' }))
    expect(await screen.findByText(/graph_unavailable: The graph could not be loaded\./)).toBeTruthy()
    expect(screen.getByRole('row', { name: /main\.py file/i })).toBeTruthy()
  })

  it('shows friendly not-ready, empty, and failed-request states', async () => {
    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Repository not ready',
      status: 409,
      detail: 'Repository analysis is not ready.',
      code: 'repository_not_ready',
      request_id: 'graph-not-ready',
    }, { status: 409, headers: { 'Content-Type': 'application/problem+json' } })))
    const notReady = renderGraph()
    expect(await screen.findByText('Analysis is still running')).toBeTruthy()
    notReady.unmount()

    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', () => graphResponse({
      nodes: [],
      edges: [],
      truncated: false,
      total_nodes: 0,
    })))
    renderGraph()
    expect(await screen.findByText('No modules at this level')).toBeTruthy()
  })

  it('shows the problem details when the graph request fails', async () => {
    server.use(http.get('/api/v1/repositories/repo-1/graph/modules', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Graph failed',
      status: 503,
      detail: 'The graph service is unavailable.',
      code: 'graph_unavailable',
      request_id: 'graph-failed',
    }, { status: 503, headers: { 'Content-Type': 'application/problem+json' } })))
    renderGraph()
    expect(await screen.findByText(/graph_unavailable: The graph service is unavailable\./)).toBeTruthy()
  })
})
