import { useCallback, useMemo, useState } from 'react'
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  Folder,
  FolderOpen,
  LoaderCircle,
  TriangleAlert,
} from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router'

import type { SymbolData, TreeFile } from '../api/client'
import { ApiError } from '../api/client'
import { useFile, useSource, useTree } from '../api/hooks'
import { Badge, Card, EmptyState, ErrorState, Skeleton } from '../components/ui'
import { RelationshipPanel } from './RelationshipPanel'
import { SourceViewer } from './SourceViewer'
import { buildSymbolOutline, resolveTargetLine } from './outline'

function TreeLevel({
  repositoryId,
  pathPrefix,
  expanded,
  selectedFileId,
  onToggleFolder,
  onSelectFile,
}: {
  repositoryId: string
  pathPrefix: string
  expanded: ReadonlySet<string>
  selectedFileId: string
  onToggleFolder: (path: string) => void
  onSelectFile: (file: TreeFile) => void
}) {
  const tree = useTree(repositoryId, pathPrefix)
  if (tree.isLoading) return <div className="tree-loading"><LoaderCircle className="spin" size={14} /> Loading…</div>
  if (tree.error) return <ErrorState error={tree.error} />
  if (!tree.data) return null
  if (!tree.data.folders.length && !tree.data.files.length) {
    return <p className="tree-empty">{pathPrefix ? 'This folder is empty.' : 'No analyzed files.'}</p>
  }
  return (
    <ul className="file-tree-list">
      {tree.data.folders.map((folder) => {
        const isExpanded = expanded.has(folder.path)
        return (
          <li key={folder.path}>
            <button
              className="tree-entry tree-folder"
              type="button"
              aria-expanded={isExpanded}
              aria-label={`${isExpanded ? 'Collapse' : 'Expand'} folder ${folder.name}`}
              onClick={() => onToggleFolder(folder.path)}
              onKeyDown={(event) => {
                if (event.key === 'ArrowRight' && !isExpanded) onToggleFolder(folder.path)
                if (event.key === 'ArrowLeft' && isExpanded) onToggleFolder(folder.path)
              }}
            >
              {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              {isExpanded ? <FolderOpen size={14} /> : <Folder size={14} />}
              <span>{folder.name}</span><small>{folder.file_count}</small>
            </button>
            {isExpanded && (
              <TreeLevel
                repositoryId={repositoryId}
                pathPrefix={folder.path}
                expanded={expanded}
                selectedFileId={selectedFileId}
                onToggleFolder={onToggleFolder}
                onSelectFile={onSelectFile}
              />
            )}
          </li>
        )
      })}
      {tree.data.files.map((file) => (
        <li key={file.file_id}>
          <button
            className={`tree-entry tree-file ${selectedFileId === file.file_id ? 'selected' : ''}`}
            type="button"
            aria-current={selectedFileId === file.file_id ? 'page' : undefined}
            onClick={() => onSelectFile(file)}
          >
            <span className="tree-indent" /><FileCode2 size={14} /><span>{file.name}</span>
            {file.parse_status === 'syntax_error' && <TriangleAlert size={12} aria-label="Syntax error" />}
          </button>
        </li>
      ))}
    </ul>
  )
}

function OutlineItems({
  items,
  onSelect,
  nested = false,
}: {
  items: ReturnType<typeof buildSymbolOutline>
  onSelect: (symbol: SymbolData) => void
  nested?: boolean
}) {
  return (
    <ul className={nested ? 'outline-list outline-nested' : 'outline-list'}>
      {items.map(({ symbol, children }) => (
        <li key={symbol.id}>
          <button
            type="button"
            className="outline-item"
            onClick={() => onSelect(symbol)}
            aria-label={`Go to ${symbol.kind} ${symbol.name}, line ${symbol.start_line}`}
          >
            <span className={`outline-kind outline-${symbol.kind}`}>{symbol.kind === 'class' ? 'C' : symbol.kind === 'method' ? 'M' : 'ƒ'}</span>
            <span>{symbol.name}</span><small>:{symbol.start_line}</small>
          </button>
          {children.length > 0 && <OutlineItems items={children} onSelect={onSelect} nested />}
        </li>
      ))}
    </ul>
  )
}

export default function ExplorerPage() {
  const { repositoryId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const fileId = searchParams.get('file') ?? ''
  const requestedLine = Number(searchParams.get('line'))
  const lineParam = Number.isInteger(requestedLine) && requestedLine > 0 ? requestedLine : null
  const [userExpanded, setUserExpanded] = useState<Set<string>>(() => new Set())
  const [userCollapsed, setUserCollapsed] = useState<Set<string>>(() => new Set())
  const [selectedSymbolId, setSelectedSymbolId] = useState<string | null>(null)
  const fileQuery = useFile(repositoryId, fileId)
  const sourceQuery = useSource(repositoryId, fileId)
  const treeQuery = useTree(repositoryId)
  const file = fileQuery.data
  const outline = useMemo(() => buildSymbolOutline(file?.symbols ?? []), [file?.symbols])
  const selectedSymbol = file?.symbols.find((symbol) => symbol.id === selectedSymbolId) ?? null

  const expanded = new Set(userExpanded)
  if (file?.path) {
    const parts = file.path.split('/')
    for (let index = 1; index < parts.length; index += 1) {
      const parentPath = parts.slice(0, index).join('/')
      if (!userCollapsed.has(parentPath)) expanded.add(parentPath)
    }
  }

  const toggleFolder = (path: string) => {
    if (expanded.has(path)) {
      setUserCollapsed((current) => new Set(current).add(path))
      setUserExpanded((current) => {
        const next = new Set(current)
        next.delete(path)
        return next
      })
    } else {
      setUserCollapsed((current) => {
        const next = new Set(current)
        next.delete(path)
        return next
      })
      setUserExpanded((current) => new Set(current).add(path))
    }
  }

  const selectFile = useCallback((nextFile: TreeFile) => {
    setSelectedSymbolId(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('file', nextFile.file_id)
      next.delete('line')
      return next
    })
  }, [setSearchParams])

  const openFileAtLine = useCallback((nextFileId: string, line: number) => {
    setSelectedSymbolId(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('file', nextFileId)
      next.set('line', String(line))
      return next
    })
  }, [setSearchParams])

  const selectSymbol = (symbol: SymbolData) => {
    setSelectedSymbolId(symbol.id)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('line', String(symbol.start_line))
      return next
    })
  }

  const lineToHighlight = resolveTargetLine(
    selectedSymbol?.start_line ?? lineParam,
    sourceQuery.data?.line_count ?? 0,
  )

  if (treeQuery.error instanceof ApiError && treeQuery.error.status === 409) {
    return <div className="page-wrap"><Card><EmptyState title="Analysis is still running" description="The file explorer will be available when repository analysis completes." action={<Link className="text-link" to="/">Back to repositories</Link>} /></Card></div>
  }
  if (treeQuery.error) return <div className="page-wrap"><ErrorState error={treeQuery.error} /></div>

  return (
    <div className="page-wrap explorer-page">
      <div className="page-heading">
        <span className="eyebrow">CODE EXPLORER</span>
        <h1>Explore the source</h1>
        <p>Browse files, inspect symbols, and follow relationships.</p>
      </div>
      <div className="explorer-layout">
        <Card className="file-tree-card">
          <div className="explorer-panel-heading"><h2>Files</h2><span>{treeQuery.data?.files.length ?? 0} at root</span></div>
          {!treeQuery.data && treeQuery.isLoading ? <Skeleton lines={6} /> : (
            <TreeLevel
              repositoryId={repositoryId}
              pathPrefix=""
              expanded={expanded}
              selectedFileId={fileId}
              onToggleFolder={toggleFolder}
              onSelectFile={selectFile}
            />
          )}
        </Card>
        <div className="explorer-main-column">
          <Card className="source-card">
            {!fileId ? (
              <EmptyState title="Select a file" description="Choose a file from the tree to read its source and symbols." />
            ) : fileQuery.isLoading || sourceQuery.isLoading ? (
              <Skeleton lines={9} />
            ) : fileQuery.error ? (
              <ErrorState error={fileQuery.error} />
            ) : sourceQuery.error instanceof ApiError && sourceQuery.error.status === 413 ? (
              <EmptyState title="Source is too large" description="This file exceeds the 1 MB viewer limit." />
            ) : sourceQuery.error instanceof ApiError && sourceQuery.error.status === 415 ? (
              <EmptyState title="Binary file" description="The source viewer only displays text files." />
            ) : sourceQuery.error ? (
              <ErrorState error={sourceQuery.error} />
            ) : file && sourceQuery.data ? (
              <>
                <div className="source-toolbar">
                  <div><FileCode2 size={15} /><span className="mono">{sourceQuery.data.path}</span></div>
                  <span>{sourceQuery.data.line_count.toLocaleString()} lines</span>
                </div>
                {file.parse_status === 'syntax_error' && (
                  <div className="parse-error-banner" role="status"><AlertCircle size={15} />This file has a syntax error. Source is shown as text; symbol analysis may be incomplete.</div>
                )}
                <SourceViewer content={sourceQuery.data.content} line={lineToHighlight} />
              </>
            ) : null}
          </Card>
          {file && (
            <Card className="relationship-card">
              <RelationshipPanel
                key={`${file.id}:${selectedSymbol?.id ?? ''}`}
                repositoryId={repositoryId}
                fileId={file.id}
                symbol={selectedSymbol}
                onOpenFile={openFileAtLine}
              />
            </Card>
          )}
        </div>
        <Card className="symbol-outline-card">
          <div className="explorer-panel-heading"><h2>Symbols</h2>{file && <Badge>{file.symbols.length}</Badge>}</div>
          {!fileId ? <p className="muted">Select a file to view its outline.</p> : fileQuery.isLoading ? <Skeleton lines={4} /> : fileQuery.error ? <ErrorState error={fileQuery.error} /> : outline.length ? <OutlineItems items={outline} onSelect={selectSymbol} /> : <p className="muted">No symbols in this file.</p>}
        </Card>
      </div>
    </div>
  )
}
