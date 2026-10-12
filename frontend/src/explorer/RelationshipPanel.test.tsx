import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import type { Edge, SymbolData } from '../api/client'
import { server } from '../test/server'
import { RelationshipPanel } from './RelationshipPanel'

const symbol: SymbolData = {
  id: 'symbol-1',
  file_id: 'file-1',
  file_path: 'src/main.py',
  kind: 'function',
  name: 'start',
  qualified_name: 'start',
  start_line: 10,
  end_line: 12,
}

function makeEdge(index: number): Edge {
  return {
    id: `edge-${index}`,
    kind: 'CALLS',
    src_file_id: 'caller-file',
    src_file: index === 20 ? 'z-last.py' : 'a-caller.py',
    src_symbol_id: 'caller-symbol',
    src_symbol: 'caller',
    dst_file_id: 'file-1',
    dst_file: 'src/main.py',
    dst_symbol_id: 'symbol-1',
    dst_symbol: 'start',
    dst_name: null,
    confidence: 'inferred',
    origin: null,
    is_constructor: false,
    line: index + 1,
  }
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <RelationshipPanel repositoryId="repo-1" fileId="file-1" symbol={symbol} onOpenFile={() => undefined} />
    </QueryClientProvider>,
  )
}

describe('symbol relationships', () => {
  it('filters by confidence and paginates results', async () => {
    const user = userEvent.setup()
    const requested: URLSearchParams[] = []
    server.use(http.get('/api/v1/repositories/repo-1/symbols/symbol-1/usages', ({ request }) => {
      const params = new URL(request.url).searchParams
      requested.push(params)
      const offset = Number(params.get('offset'))
      return HttpResponse.json({
        items: offset === 0 ? Array.from({ length: 20 }, (_, index) => makeEdge(index)) : [makeEdge(20)],
        total: 21,
      })
    }))
    renderPanel()

    expect(await screen.findByRole('heading', { name: 'a-caller.py' })).toBeTruthy()
    expect(requested[0]?.get('min_confidence')).toBe('inferred')
    await user.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('heading', { name: 'z-last.py' })).toBeTruthy()
    expect(requested.some((params) => params.get('offset') === '20')).toBe(true)

    await user.selectOptions(screen.getByLabelText('Minimum confidence'), 'exact')
    await waitFor(() => expect(requested.some((params) => params.get('min_confidence') === 'exact')).toBe(true))
  })
})
