import { useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, ChevronDown, ChevronRight, LoaderCircle } from 'lucide-react'

import type { Edge, MinimumConfidence, SymbolData } from '../api/client'
import { api } from '../api/client'
import {
  useFileImportEdges,
  useSymbolEdges,
} from '../api/hooks'
import { ConfidenceBadge, ErrorState } from '../components/ui'

type Tab = 'Usages' | 'Callers' | 'Callees' | 'Imported by' | 'Imports'
const symbolTabs: Tab[] = ['Usages', 'Callers', 'Callees']
const pageSize = 20

function relationshipFor(tab: Tab): 'usages' | 'callers' | 'callees' {
  return tab.toLowerCase() as 'usages' | 'callers' | 'callees'
}

function edgeTarget(edge: Edge, tab: Tab): { fileId: string | null; path: string } {
  if (tab === 'Callees') {
    return { fileId: edge.dst_file_id, path: edge.dst_file ?? edge.dst_name ?? 'External target' }
  }
  return { fileId: edge.src_file_id, path: edge.src_file }
}

function EdgeRow({
  edge,
  tab,
  repositoryId,
  minConfidence,
  onOpen,
  expand,
}: {
  edge: Edge
  tab: Tab
  repositoryId: string
  minConfidence: MinimumConfidence
  onOpen: (fileId: string, line: number) => void
  expand?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const target = edgeTarget(edge, tab)
  const targetFileId = target.fileId
  return (
    <div className="relationship-row">
      <div className="relationship-edge">
        {targetFileId ? (
          <button type="button" className="relationship-file" onClick={() => onOpen(targetFileId, edge.line)}>
            {target.path}
          </button>
        ) : <span className="relationship-file">{target.path}</span>}
        <span className="relationship-signal"><ConfidenceBadge value={edge.confidence} /><span>line {edge.line}</span></span>
      </div>
      {expand && edge.dst_symbol_id && (
        <button
          type="button"
          className="relationship-expand"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {expanded ? 'Hide callees' : 'Expand callees'}
        </button>
      )}
      {expanded && edge.dst_symbol_id && targetFileId && (
        <ExpandedCallees
          repositoryId={repositoryId}
          symbolId={edge.dst_symbol_id}
          minConfidence={minConfidence}
          onOpen={onOpen}
        />
      )}
    </div>
  )
}

function ExpandedCallees({
  repositoryId,
  symbolId,
  minConfidence,
  onOpen,
}: {
  repositoryId: string
  symbolId: string
  minConfidence: MinimumConfidence
  onOpen: (fileId: string, line: number) => void
}) {
  const query = useSymbolEdges(repositoryId, symbolId, 'callees', {
    minConfidence,
    limit: pageSize,
  })
  if (query.isLoading) return <span className="muted relationship-nested-loading">Loading callees…</span>
  if (query.error) return <ErrorState error={query.error} />
  if (!query.data?.items.length) return <span className="muted relationship-nested-loading">No callees found.</span>
  return (
    <div className="relationship-nested" aria-label="One-level callees">
      {query.data.items.map((edge) => {
        const fileId = edge.dst_file_id
        return (
          <div className="relationship-edge" key={edge.id}>
            {fileId
              ? <button type="button" className="relationship-file" onClick={() => onOpen(fileId, edge.line)}>{edge.dst_file ?? edge.dst_name}</button>
              : <span className="relationship-file">{edge.dst_name ?? 'External target'}</span>}
            <span className="relationship-signal"><ConfidenceBadge value={edge.confidence} /><span>line {edge.line}</span></span>
          </div>
        )
      })}
    </div>
  )
}

export function RelationshipPanel({
  repositoryId,
  fileId,
  symbol,
  onOpenFile,
}: {
  repositoryId: string
  fileId: string
  symbol: SymbolData | null
  onOpenFile: (fileId: string, line: number) => void
}) {
  const [tab, setTab] = useState<Tab>(symbol ? 'Usages' : 'Imports')
  const [minConfidence, setMinConfidence] = useState<MinimumConfidence>('inferred')
  const [extraItems, setExtraItems] = useState<Edge[]>([])
  const [loadedCount, setLoadedCount] = useState(0)
  const [moreLoading, setMoreLoading] = useState(false)
  const [moreError, setMoreError] = useState<unknown>(null)
  const isSymbolTab = symbolTabs.includes(tab)
  const symbolQuery = useSymbolEdges(
    repositoryId,
    isSymbolTab ? symbol?.id ?? '' : '',
    isSymbolTab ? relationshipFor(tab) : 'usages',
    { minConfidence, limit: pageSize, offset: 0 },
  )
  const fileRelation = tab === 'Imported by' ? 'imported-by' : 'imports'
  const fileQuery = useFileImportEdges(
    repositoryId,
    isSymbolTab ? '' : fileId,
    fileRelation,
    { minConfidence, limit: pageSize, offset: 0 },
  )
  const query = isSymbolTab ? symbolQuery : fileQuery
  const baseCount = query.data?.items.length ?? 0
  const items = useMemo(
    () => [...(query.data?.items ?? []), ...extraItems],
    [extraItems, query.data?.items],
  )

  const groupedUsages = useMemo(() => {
    if (tab !== 'Usages') return []
    const groups = new Map<string, Edge[]>()
    for (const edge of items) {
      const group = groups.get(edge.src_file) ?? []
      group.push(edge)
      groups.set(edge.src_file, group)
    }
    return [...groups.entries()]
  }, [items, tab])

  const selectTab = (next: Tab) => {
    if (symbol && !symbolTabs.includes(next)) return
    setExtraItems([])
    setLoadedCount(0)
    setMoreError(null)
    setTab(next)
  }
  const selectConfidence = (next: MinimumConfidence) => {
    setExtraItems([])
    setLoadedCount(0)
    setMoreError(null)
    setMinConfidence(next)
  }
  const loadMore = async () => {
    setMoreLoading(true)
    setMoreError(null)
    try {
      const nextOffset = baseCount + loadedCount
      const page = isSymbolTab
        ? await api.symbolEdges(repositoryId, symbol?.id ?? '', relationshipFor(tab), {
            minConfidence,
            limit: pageSize,
            offset: nextOffset,
          })
        : await api.fileImportEdges(repositoryId, fileId, fileRelation, {
            minConfidence,
            limit: pageSize,
            offset: nextOffset,
          })
      setExtraItems((current) => [...current, ...page.items])
      setLoadedCount((current) => current + page.items.length)
    } catch (error) {
      setMoreError(error)
    } finally {
      setMoreLoading(false)
    }
  }
  return (
    <section className="relationship-panel" aria-label="File relationships">
      <div className="section-title">
        <div><h2>{symbol ? symbol.name : 'Relationships'}</h2><p>{symbol ? symbol.qualified_name : 'Imports and usages'}</p></div>
      </div>
      <div className="relationship-tabs" role="tablist" aria-label="Relationship type">
        {(symbol ? symbolTabs : ['Imports', 'Imported by', ...symbolTabs] as Tab[]).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? 'relationship-tab active' : 'relationship-tab'}
            onClick={() => selectTab(name)}
          >{name}</button>
        ))}
      </div>
      <label className="confidence-control">
        Minimum confidence
        <select
          value={minConfidence === 'unresolved' ? 'all' : minConfidence}
          onChange={(event) => {
            selectConfidence(event.target.value === 'all' ? 'unresolved' : event.target.value as MinimumConfidence)
          }}
        >
          <option value="exact">Exact</option>
          <option value="inferred">Inferred</option>
          <option value="all">All</option>
        </select>
      </label>
      <p className="analysis-note"><ArrowDownRight size={14} /> Dynamic calls are not guessed.</p>
      {query.isLoading ? (
        <div className="relationship-loading"><LoaderCircle className="spin" size={16} /> Loading relationships…</div>
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : items.length === 0 ? (
        <p className="muted relationship-empty">No relationships at this confidence level.</p>
      ) : tab === 'Usages' ? (
        <div className="relationship-results">
          {groupedUsages.map(([path, edges]) => (
            <section key={path} className="relationship-group">
              <h3><ArrowUpRight size={13} />{path}</h3>
              {edges.map((edge) => <EdgeRow key={edge.id} edge={edge} tab={tab} repositoryId={repositoryId} minConfidence={minConfidence} onOpen={onOpenFile} />)}
            </section>
          ))}
        </div>
      ) : (
        <div className="relationship-results">
          {items.map((edge) => (
            <EdgeRow
              key={edge.id}
              edge={edge}
              tab={tab}
              repositoryId={repositoryId}
              minConfidence={minConfidence}
              onOpen={onOpenFile}
              expand={tab === 'Callees'}
            />
          ))}
        </div>
      )}
      {moreError ? <ErrorState error={moreError} /> : null}
      {query.data && baseCount + loadedCount < query.data.total && (
        <button
          className="button relationship-more"
          type="button"
          onClick={() => void loadMore()}
          disabled={moreLoading}
        >{moreLoading ? 'Loading…' : 'Load more'}</button>
      )}
    </section>
  )
}
