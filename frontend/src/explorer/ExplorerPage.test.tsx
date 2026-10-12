import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { FileData, SymbolData } from '../api/client'
import { server } from '../test/server'
import ExplorerPage from './ExplorerPage'
import { buildSymbolOutline, resolveTargetLine } from './outline'

const symbol = {
  id: 'symbol-1',
  file_id: 'file-1',
  file_path: 'pkg/main.py',
  kind: 'class',
  name: 'Runner',
  qualified_name: 'Runner',
  start_line: 2,
  end_line: 8,
} satisfies SymbolData

const file = {
  id: 'file-1',
  path: 'pkg/main.py',
  loc: 8,
  is_entry_point: true,
  parse_status: 'ok',
  symbols: [symbol],
} satisfies FileData

function Location() {
  const location = useLocation()
  return <output aria-label="Current URL">{location.pathname}{location.search}</output>
}

function renderExplorer(url = '/repositories/repo-1/explorer') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Location />
        <Routes>
          <Route path="/repositories/:repositoryId/explorer" element={<ExplorerPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function treeResponse(pathPrefix: string | null) {
  return HttpResponse.json(pathPrefix === 'pkg'
    ? { folders: [], files: [{ file_id: 'file-1', name: 'main.py', path: 'pkg/main.py', loc: 8, parse_status: 'ok' }] }
    : { folders: [{ name: 'pkg', path: 'pkg', file_count: 1 }], files: [] })
}

describe('code explorer', () => {
  it('expands the lazy file tree and syncs the selected file to the URL', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/v1/repositories/repo-1/tree', ({ request }) =>
        treeResponse(new URL(request.url).searchParams.get('path_prefix'))),
      http.get('/api/v1/repositories/repo-1/files/file-1', () => HttpResponse.json(file)),
      http.get('/api/v1/repositories/repo-1/files/file-1/source', () => HttpResponse.json({
        path: 'pkg/main.py',
        language: 'python',
        content: 'class Runner:\\n    pass\\n',
        line_count: 2,
      })),
      http.get('/api/v1/repositories/repo-1/files/file-1/imports', () => HttpResponse.json({ items: [], total: 0 })),
    )
    renderExplorer()

    await user.click(await screen.findByRole('button', { name: 'Expand folder pkg' }))
    await user.click(await screen.findByRole('button', { name: /main\.py/ }))
    await waitFor(() => expect(screen.getByLabelText('Current URL').textContent).toContain('?file=file-1'))
    expect(await screen.findByRole('button', { name: 'Go to class Runner, line 2' })).toBeTruthy()
    expect(screen.getByText('pkg/main.py')).toBeTruthy()
  })

  it('shows a friendly not-ready state when the tree is unavailable', async () => {
    server.use(http.get('/api/v1/repositories/repo-1/tree', () => HttpResponse.json({
      type: 'about:blank',
      title: 'Repository not ready',
      status: 409,
      detail: 'Repository analysis is not ready.',
      code: 'repository_not_ready',
      request_id: 'tree-test',
    }, { status: 409, headers: { 'Content-Type': 'application/problem+json' } })))
    renderExplorer()
    expect(await screen.findByText('The file explorer will be available when repository analysis completes.')).toBeTruthy()
  })

  it.each([
    [413, 'Source is too large'],
    [415, 'Binary file'],
  ])('handles source status %i with a friendly message', async (status, title) => {
    server.use(
      http.get('/api/v1/repositories/repo-1/tree', () =>
        HttpResponse.json({ folders: [], files: [{ file_id: 'file-1', name: 'main.py', path: 'main.py', loc: 8, parse_status: 'ok' }] })),
      http.get('/api/v1/repositories/repo-1/files/file-1', () => HttpResponse.json({ ...file, path: 'main.py' })),
      http.get('/api/v1/repositories/repo-1/files/file-1/source', () => HttpResponse.json({
        type: 'about:blank',
        title: 'Source cannot be displayed',
        status,
        detail: 'Source was rejected.',
        code: status === 413 ? 'source_too_large' : 'binary_source',
        request_id: 'source-test',
      }, { status, headers: { 'Content-Type': 'application/problem+json' } })),
      http.get('/api/v1/repositories/repo-1/files/file-1/imports', () => HttpResponse.json({ items: [], total: 0 })),
    )
    renderExplorer('/repositories/repo-1/explorer?file=file-1')
    expect(await screen.findByText(title)).toBeTruthy()
  })
})

describe('explorer navigation helpers', () => {
  it('nests methods under their class and clamps requested source lines', () => {
    const method: SymbolData = {
      ...symbol,
      id: 'method-1',
      kind: 'method',
      name: 'run',
      qualified_name: 'Runner.run',
      start_line: 4,
      end_line: 6,
    }
    const outline = buildSymbolOutline([method, symbol])
    expect(outline[0]?.children[0]?.symbol.name).toBe('run')
    expect(resolveTargetLine(15, 8)).toBe(8)
    expect(resolveTargetLine(-3, 8)).toBe(1)
    expect(resolveTargetLine(null, 8)).toBeNull()
  })
})
