import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { AlertCircle, ArrowDown, ArrowUp, FileCode2, LoaderCircle, Search, X } from 'lucide-react'
import { useNavigate } from 'react-router'

import type { SearchResult } from '../api/client'
import { ApiError, api } from '../api/client'
import { useSearch } from '../api/hooks'
import { ErrorState } from '../components/ui'

type SearchKind = 'file' | 'class' | 'function' | 'method'

function matchesKind(result: SearchResult, kind: SearchKind): boolean {
  if (kind === 'file') return result.kind === 'file'
  return result.kind === 'symbol' && result.symbol_kind === kind
}

export function CommandPalette({
  repositoryId,
  onClose,
}: {
  repositoryId: string
  onClose: () => void
}) {
  const dialog = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [kind, setKind] = useState<SearchKind | 'all'>('all')
  const [activeIndex, setActiveIndex] = useState(0)
  const [opening, setOpening] = useState(false)
  const [openError, setOpenError] = useState<unknown>(null)

  useEffect(() => {
    input.current?.focus()
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 200)
    return () => window.clearTimeout(timer)
  }, [query])

  const search = useSearch(repositoryId, debouncedQuery, 50)
  const results = useMemo(
    () => (search.data?.items ?? []).filter((result) => kind === 'all' || matchesKind(result, kind)),
    [kind, search.data],
  )

  const openResult = async (result: SearchResult) => {
    setOpenError(null)
    setOpening(true)
    try {
      let line: number | null = null
      if (result.symbol_id) {
        const file = await api.file(repositoryId, result.file_id)
        line = file.symbols.find((symbol) => symbol.id === result.symbol_id)?.start_line ?? null
      }
      const queryString = new URLSearchParams({ file: result.file_id })
      if (line !== null) queryString.set('line', String(line))
      onClose()
      navigate(`/repositories/${repositoryId}/explorer?${queryString.toString()}`)
    } catch (error) {
      setOpenError(error)
    } finally {
      setOpening(false)
    }
  }

  const handleKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((current) => Math.min(current + 1, Math.max(results.length - 1, 0)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((current) => Math.max(current - 1, 0))
    } else if (event.key === 'Enter' && results[activeIndex]) {
      event.preventDefault()
      void openResult(results[activeIndex])
    } else if (event.key === 'Tab') {
      const focusable = dialog.current?.querySelectorAll<HTMLElement>(
        'input:not([disabled]), button:not([disabled])',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first?.focus()
      }
    }
  }

  const queryError = openError ?? search.error
  const isWildcardOnly = query.length > 0 && /^[%_\\\s]+$/.test(query)

  return (
    <div className="palette-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div
        ref={dialog}
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby="command-title"
        onKeyDown={handleKeys}
      >
        <div className="palette-search-row">
          <Search size={18} aria-hidden="true" />
          <label className="visually-hidden" htmlFor="command-query">Search files and symbols</label>
          <input
            ref={input}
            id="command-query"
            autoComplete="off"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setActiveIndex(0)
            }}
            placeholder="Search files and symbols…"
          />
          {search.isFetching && <LoaderCircle className="spin" size={15} aria-label="Searching" />}
          <button type="button" className="icon-button" aria-label="Close search" onClick={onClose}><X size={16} /></button>
        </div>
        <h2 id="command-title" className="visually-hidden">Search this repository</h2>
        <div className="palette-filters" aria-label="Filter search results">
          {(['all', 'file', 'class', 'function', 'method'] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={kind === value}
              className={kind === value ? 'palette-chip active' : 'palette-chip'}
              onClick={() => {
                setKind(value)
                setActiveIndex(0)
              }}
            >{value === 'all' ? 'All' : value}</button>
          ))}
        </div>
        <div className="palette-results" role="listbox" aria-label="Search results">
          {queryError ? <ErrorState error={queryError} /> : query.trim().length < 2 ? (
            <p className="palette-hint">{isWildcardOnly ? 'Enter a file or symbol name; wildcards are treated literally.' : 'Type at least 2 characters to search.'}</p>
          ) : search.isLoading || search.isFetching ? (
            <p className="palette-hint"><LoaderCircle className="spin" size={15} /> Searching…</p>
          ) : !results.length ? (
            <p className="palette-hint">No matching files or symbols.</p>
          ) : results.map((result, index) => (
            <button
              type="button"
              role="option"
              aria-selected={activeIndex === index}
              className={`palette-result ${activeIndex === index ? 'active' : ''}`}
              key={`${result.kind}:${result.symbol_id ?? result.file_id}:${result.name}`}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => void openResult(result)}
              disabled={opening}
            >
              <FileCode2 size={15} />
              <span className="palette-result-main"><strong>{result.name}</strong><small className="mono">{result.path}{result.qualified_name ? ` · ${result.qualified_name}` : ''}</small></span>
              <span className="palette-result-kind">{result.kind === 'file' ? 'file' : result.symbol_kind ?? 'symbol'}</span>
            </button>
          ))}
        </div>
        {opening && <p className="palette-opening"><LoaderCircle className="spin" size={14} />Opening result…</p>}
        {openError instanceof ApiError && <p className="palette-inline-error"><AlertCircle size={13} />{openError.code}: {openError.message}</p>}
        <footer className="palette-footer"><span><ArrowUp size={12} /><ArrowDown size={12} /> Navigate</span><span>Enter to open</span><span>Esc to close</span></footer>
      </div>
    </div>
  )
}
