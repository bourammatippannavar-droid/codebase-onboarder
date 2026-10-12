import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  getBezierPath,
  useReactFlow,
} from '@xyflow/react'
import type { EdgeProps, NodeProps } from '@xyflow/react'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  CircleDot,
  FileCode2,
  Folder,
  FolderOpen,
  GitFork,
  LoaderCircle,
  RotateCcw,
  ShieldAlert,
  X,
} from 'lucide-react'
import {
  Link,
  useParams,
  useSearchParams,
} from 'react-router'

import type { ModuleEdge, ModuleGraph, ModuleNode } from '../api/client'
import { ApiError } from '../api/client'
import { useFileRelations, useModuleGraph } from '../api/hooks'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
} from '../components/ui'
import {
  buildFlow,
  layoutFlow,
} from './flow'
import type { FlowEdge, FlowNode, FlowNodeData } from './flow'

type InteractiveNodeData = FlowNodeData & {
  onActivate?: () => void
  onMoveFocus?: (direction: string) => void
}
type InteractiveNode = FlowNode & { data: InteractiveNodeData }
type InteractiveEdge = FlowEdge

function FileRole({ icon, label }: { icon: ReactNode; label: string }) {
  return <Badge>{icon}{label}</Badge>
}

function ModuleNodeView({ data }: NodeProps<InteractiveNode>) {
  const module = data.module
  const folder = module.kind === 'folder'
  const outside = module.kind === 'outside'
  const flags = [
    !folder && !outside && module.is_entry_point
      ? <FileRole key="entry" icon={<Check size={11} />} label="entry point" />
      : null,
    !folder && !outside && module.central
      ? <FileRole key="central" icon={<ShieldAlert size={11} />} label="central" />
      : null,
    module.in_cycle
      ? <FileRole key="cycle" icon={<CircleDot size={11} />} label="in cycle" />
      : null,
    folder || outside
      ? <FileRole key="folder" icon={<Folder size={11} />} label={folder ? "folder" : "outside"} />
      : null,
  ].filter((item) => item !== null)

  return (
    <div
      className={[
        'graph-node',
        folder ? 'graph-folder-node' : '',
        outside ? 'graph-outside-node' : '',
        module.in_cycle ? 'node-cycle' : '',
        !folder && !outside && module.central ? 'node-central' : '',
        data.selected ? 'node-selected' : '',
        data.neighbor ? 'node-neighbor' : '',
        data.dimmed ? 'node-dimmed' : '',
      ].filter(Boolean).join(' ')}
      role="button"
      tabIndex={0}
      aria-label={`${module.kind}: ${module.path}${module.in_cycle ? ', in cycle' : ''}`}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          data.onActivate?.()
        } else if (event.key.startsWith('Arrow')) {
          event.preventDefault()
          data.onMoveFocus?.(event.key)
        }
      }}
    >
      <Handle className="graph-node-handle" type="target" position={Position.Left} />
      <div className="graph-node-heading">
        <span className={`graph-node-icon ${folder ? 'folder-tone' : outside ? 'outside-tone' : ''}`}>
          {folder ? <FolderOpen size={17} /> : outside ? <Folder size={16} /> : <FileCode2 size={16} />}
        </span>
        <span className="graph-node-kind">{folder ? 'MODULE' : outside ? 'OUTSIDE SCOPE' : 'SOURCE FILE'}</span>
        {module.in_cycle && <CircleDot className="cycle-indicator" size={14} aria-label="In cycle" />}
      </div>
      <strong className="graph-node-name">{module.name}</strong>
      <span className="graph-node-path mono">{folder && module.path === '.' ? 'Top level' : module.path}</span>
      <div className="graph-node-footer">
        {folder || outside
          ? <span>{module.file_count} files · {module.loc.toLocaleString()} LOC</span>
          : <span>{module.loc.toLocaleString()} LOC · {module.imported_by} importers</span>}
        {flags.length > 0 && <span className="graph-node-flags">{flags}</span>}
      </div>
      <Handle className="graph-node-handle" type="source" position={Position.Right} />
    </div>
  )
}

function ModuleEdgeView({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<InteractiveEdge>) {
  const edgeData = data ?? { count: 1, inCycle: false, hovered: false, dimmed: false }
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })
  const color = edgeData.inCycle ? 'var(--red)' : 'var(--edge-color)'
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: color,
          strokeWidth: Math.min(1.5 + edgeData.count, 5),
          strokeDasharray: edgeData.inCycle ? '5 4' : undefined,
          opacity: edgeData.dimmed ? 0.12 : 0.8,
        }}
      />
      {edgeData.hovered && (
        <EdgeLabelRenderer>
          <span
            className="module-edge-count nodrag nopan"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)` }}
          >{edgeData.count} import{edgeData.count === 1 ? '' : 's'}</span>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

const nodeTypes = { module: ModuleNodeView }
const edgeTypes = { module: ModuleEdgeView }

function FitViewButton() {
  const flow = useReactFlow()
  return (
    <button
      className="fit-view-control"
      type="button"
      aria-label="Fit graph to view"
      onClick={() => void flow.fitView({ padding: 0.2, duration: 0 })}
    ><RotateCcw size={13} /> Fit</button>
  )
}

function Breadcrumbs({ path, repositoryId }: { path: string; repositoryId: string }) {
  const [searchParams] = useSearchParams()
  const segments = path ? path.split('/') : []
  const pathUrl = (nextPath: string) => {
    const next = new URLSearchParams(searchParams)
    if (nextPath) next.set('path', nextPath)
    else next.delete('path')
    next.delete('selected')
    const query = next.toString()
    return `/repositories/${repositoryId}/graph${query ? `?${query}` : ''}`
  }
  return (
    <nav className="graph-breadcrumbs" aria-label="Module path">
      <Link to={pathUrl('')}>All modules</Link>
      {segments.map((segment, index) => {
        const current = segments.slice(0, index + 1).join('/')
        return (
          <span className="graph-crumb-segment" key={current}>
            <ChevronRight size={13} aria-hidden="true" />
            <Link to={pathUrl(current)} aria-current={index === segments.length - 1 ? 'page' : undefined}>
              {segment}
            </Link>
          </span>
        )
      })}
    </nav>
  )
}

function Legend() {
  return (
    <div className="graph-legend" aria-label="Graph legend">
      <span><Check size={13} /> Entry point</span>
      <span><ShieldAlert size={13} /> Central</span>
      <span className="legend-cycle"><CircleDot size={13} /> In cycle</span>
      <span><Folder size={13} /> Folder</span>
    </div>
  )
}

function ModuleList({
  nodes,
  edges,
  onSelect,
  onDrill,
}: {
  nodes: FlowNode[]
  edges: ModuleEdge[]
  onSelect: (node: ModuleNode) => void
  onDrill: (path: string) => void
}) {
  const moduleNodes = nodes.map((node) => node.data.module)
  return (
    <div className="graph-list-view">
      <table aria-label="Dependency graph nodes">
        <thead><tr><th>Node</th><th>Type</th><th>Files</th><th>Lines</th><th>Signals</th></tr></thead>
        <tbody>
          {moduleNodes.map((node) => (
            <tr className={nodes.find((flowNode) => flowNode.id === node.id)?.data.dimmed ? 'graph-list-dimmed' : ''} key={node.id} tabIndex={0} onClick={() => onSelect(node)} onDoubleClick={() => { if (node.kind === 'folder') onDrill(node.path) }} onKeyDown={(event) => { if (event.key === 'Enter') onSelect(node); if (event.key === 'ArrowDown') (event.currentTarget.nextElementSibling as HTMLElement | null)?.focus(); if (event.key === 'ArrowUp') (event.currentTarget.previousElementSibling as HTMLElement | null)?.focus() }}>
              <td className="mono">{node.path}</td>
              <td>{node.kind}</td>
              <td>{node.kind === 'file' ? '1' : node.file_count}</td>
              <td>{node.loc}</td>
              <td>{node.in_cycle ? 'In cycle' : node.kind === 'file' && node.central ? 'Central' : node.kind === 'file' && node.is_entry_point ? 'Entry point' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table aria-label="Dependency graph edges">
        <thead><tr><th>Source</th><th>Target</th><th>Imports</th><th>Signals</th></tr></thead>
        <tbody>
          {edges.map((edge) => (
            <tr key={`${edge.source}-${edge.target}`}>
              <td className="mono">{nodes.find((node) => node.id === edge.source)?.data.module.path ?? edge.source}</td>
              <td className="mono">{nodes.find((node) => node.id === edge.target)?.data.module.path ?? edge.target}</td>
              <td>{edge.count}</td>
              <td>{edge.in_cycle ? 'In cycle' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DetailPanel({
  selected,
  graph,
  repositoryId,
  onClose,
  onShowBlastRadius,
  blastLoading,
}: {
  selected: ModuleNode
  graph: ModuleGraph
  repositoryId: string
  onClose: () => void
  onShowBlastRadius: () => void
  blastLoading: boolean
}) {
  const incoming = graph.edges.filter((edge) => edge.target === selected.id)
  const outgoing = graph.edges.filter((edge) => edge.source === selected.id)
  const nameById = new Map(graph.nodes.map((node) => [node.id, node.path]))
  return (
    <aside className="graph-detail-panel" aria-label="Selected node details">
      <div className="detail-panel-heading">
        <div><span className="eyebrow">NODE DETAILS</span><h2>{selected.name}</h2></div>
        <button className="icon-button" type="button" aria-label="Close details" onClick={onClose}><X size={16} /></button>
      </div>
      <p className="mono detail-path">{selected.path}</p>
      <div className="detail-stat-grid">
        <div><strong>{selected.kind === 'file' ? 1 : selected.file_count}</strong><span>files</span></div>
        <div><strong>{selected.loc.toLocaleString()}</strong><span>lines</span></div>
        <div><strong>{incoming.reduce((sum, edge) => sum + edge.count, 0)}</strong><span>imported by</span></div>
        <div><strong>{outgoing.reduce((sum, edge) => sum + edge.count, 0)}</strong><span>imports</span></div>
      </div>
      <div className="detail-flags">
        {selected.kind === 'file' && selected.is_entry_point && <Badge tone="good"><Check size={11} />entry point</Badge>}
        {selected.kind === 'file' && selected.central && <Badge tone="warn"><ShieldAlert size={11} />central</Badge>}
        {selected.in_cycle && <Badge tone="bad"><CircleDot size={11} />in cycle</Badge>}
        {selected.kind !== 'file' && <Badge><Folder size={11} />{selected.kind}</Badge>}
      </div>
      <div className="detail-relations">
        <h3>Imports</h3>
        {outgoing.length ? outgoing.map((edge) => <p key={edge.target}>{nameById.get(edge.target) ?? edge.target} <span>×{edge.count}</span></p>) : <p className="muted">No visible dependencies</p>}
        <h3>Imported by</h3>
        {incoming.length ? incoming.map((edge) => <p key={edge.source}>{nameById.get(edge.source) ?? edge.source} <span>×{edge.count}</span></p>) : <p className="muted">No visible dependents</p>}
      </div>
      {selected.kind === 'file' && (
        <div className="detail-actions">
          <Button className="blast-button" type="button" onClick={onShowBlastRadius} disabled={blastLoading}>
            {blastLoading ? <LoaderCircle className="spin" size={15} /> : <GitFork size={15} />}
            {blastLoading ? 'Loading impact…' : 'Show blast radius'}
          </Button>
          <Link className="text-link" to={`/repositories/${repositoryId}/explorer?file=${encodeURIComponent(selected.file_id)}`}>
            Open in Explorer <ArrowRight size={14} />
          </Link>
        </div>
      )}
    </aside>
  )
}

function GraphCanvas({
  nodes,
  edges,
  onNodeClick,
  onNodeDrill,
  onNodeEnter,
  onNodeLeave,
  onEdgeEnter,
  onEdgeLeave,
}: {
  nodes: InteractiveNode[]
  edges: InteractiveEdge[]
  onNodeClick: (node: ModuleNode) => void
  onNodeDrill: (node: ModuleNode) => void
  onNodeEnter: (nodeId: string) => void
  onNodeLeave: () => void
  onEdgeEnter: (edgeId: string) => void
  onEdgeLeave: () => void
}) {
  return (
    <div className="graph-canvas" aria-label="Interactive module dependency graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={1.7}
        onNodeClick={(_, node) => onNodeClick(node.data.module)}
        onNodeDoubleClick={(_, node) => onNodeDrill(node.data.module)}
        onNodeMouseEnter={(_, node) => onNodeEnter(node.id)}
        onNodeMouseLeave={onNodeLeave}
        onEdgeMouseEnter={(_, edge) => onEdgeEnter(edge.id)}
        onEdgeMouseLeave={onEdgeLeave}
      >
        <Background color="var(--flow-dots)" gap={22} size={1} />
        <MiniMap
          nodeColor={(node) => {
            const module = (node.data as FlowNodeData).module
            return module.in_cycle ? 'var(--red)' : module.kind === 'folder' ? 'var(--accent-a)' : 'var(--flow-minimap-node)'
          }}
          maskColor="var(--flow-mask)"
          pannable
          zoomable
        />
        <Controls showInteractive={false} />
        <Panel position="top-right"><FitViewButton /></Panel>
      </ReactFlow>
    </div>
  )
}

export function GraphPage() {
  const { repositoryId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const pathPrefix = searchParams.get('path') ?? ''
  const includeTests = searchParams.get('include_tests') === 'true'
  const [filter, setFilter] = useState('')
  const selectedId = searchParams.get('selected')
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)
  const [hoveredEdge, setHoveredEdge] = useState<string | null>(null)
  const [blastFileId, setBlastFileId] = useState<string | null>(null)
  const graphQuery = useModuleGraph(repositoryId, pathPrefix, includeTests)
  const blastQuery = useFileRelations(
    repositoryId,
    blastFileId ?? '',
    'dependents',
    { transitive: true, depth: 5, limit: 200, offset: 0 },
  )
  const graph = graphQuery.data
  const selectedModule = graph?.nodes.find((node) => node.id === selectedId) ?? null
  const affectedFileIds = useMemo(() => {
    if (!blastFileId || !blastQuery.isSuccess) return undefined
    return new Set([
      blastFileId,
      ...blastQuery.data.items.map((file) => file.id),
    ])
  }, [blastFileId, blastQuery.data, blastQuery.isSuccess])
  const affectedPaths = useMemo(() => {
    if (!blastFileId || !blastQuery.isSuccess || !graph) return undefined
    const selectedPath = graph.nodes.find(
      (node) => node.kind === 'file' && node.file_id === blastFileId,
    )?.path
    return new Set([
      ...(selectedPath ? [selectedPath] : []),
      ...blastQuery.data.items.map((file) => file.path),
    ])
  }, [blastFileId, blastQuery.data, blastQuery.isSuccess, graph])

  const neighbors = useMemo(() => {
    if (!hoveredNode || !graph) return new Set<string>()
    return new Set(
      graph.edges
        .filter((edge) => edge.source === hoveredNode || edge.target === hoveredNode)
        .flatMap((edge) => [edge.source, edge.target]),
    )
  }, [graph, hoveredNode])

  const onPathChange = useCallback((path: string) => {
    setBlastFileId(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (path) next.set('path', path)
      else next.delete('path')
      next.delete('selected')
      return next
    })
  }, [setSearchParams])
  const setSelectedId = useCallback((id: string | null) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (id) next.set('selected', id)
      else next.delete('selected')
      return next
    }, { replace: true })
  }, [setSearchParams])

  const flowData = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] }
    return layoutFlow(
      ...(() => {
        const base = buildFlow(graph, {
          selectedId,
          filter,
          neighborIds: neighbors,
          ...(affectedFileIds ? { affectedFileIds } : {}),
          ...(affectedPaths ? { affectedPaths } : {}),
          hoveredEdgeId: hoveredEdge,
        })
        const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
        return [
          base.nodes,
          base.edges.map((edge) => ({
            ...edge,
            animated: !reduceMotion,
            style: {
              stroke: edge.data?.inCycle ? 'var(--red)' : 'var(--edge-color)',
              strokeWidth: Math.min(1.5 + (edge.data?.count ?? 1), 5),
              strokeDasharray: edge.data?.inCycle ? '5 4' : undefined,
            },
          })),
        ] as const
      })(),
    )
  }, [affectedFileIds, affectedPaths, filter, graph, hoveredEdge, neighbors, selectedId])

  const visibleNodes: InteractiveNode[] = flowData.nodes.map((node) => ({
    ...node,
    data: {
      ...node.data,
      onActivate: () => {
        if (node.data.module.kind === 'folder') onPathChange(node.data.module.path)
        else setSelectedId(node.id)
      },
      onMoveFocus: (direction) => {
        const index = flowData.nodes.findIndex((item) => item.id === node.id)
        const delta = direction === 'ArrowLeft' || direction === 'ArrowUp' ? -1 : 1
        const target = flowData.nodes[(index + delta + flowData.nodes.length) % flowData.nodes.length]
        if (target) document.querySelector<HTMLElement>(`.react-flow__node[data-id="${CSS.escape(target.id)}"]`)?.focus()
      },
    },
  }))

  useEffect(() => {
    if (selectedId && graph && !graph.nodes.some((node) => node.id === selectedId)) {
      setSelectedId(null)
    }
  }, [graph, selectedId, setSelectedId])

  if (graphQuery.isLoading) {
    return <div className="page-wrap"><Skeleton lines={7} /></div>
  }
  if (graphQuery.error instanceof ApiError && graphQuery.error.status === 409) {
    return <div className="page-wrap"><Card><EmptyState title="Analysis is still running" description="The module graph will be available when repository analysis completes." action={<Link className="text-link" to="/">Back to repositories <ArrowRight size={14} /></Link>} /></Card></div>
  }
  if (graphQuery.error) return <div className="page-wrap"><ErrorState error={graphQuery.error} /></div>
  if (!graph) return null

  const affectedCount = blastQuery.isSuccess ? blastQuery.data.total : 0
  const onNodeSelect = (node: ModuleNode) => {
    setSelectedId(node.id)
  }
  const onDrill = (node: ModuleNode) => {
    if (node.kind === 'folder') onPathChange(node.path)
  }
  const onBlast = () => {
    if (selectedModule?.kind === 'file') {
      setBlastFileId(selectedModule.file_id)
    }
  }

  return (
    <div className="page-wrap graph-page">
      <div className="graph-page-heading">
        <div className="page-heading">
          <span className="eyebrow">DEPENDENCY MAP</span>
          <h1>Explore how modules connect</h1>
          <p>Follow imports across folders, then inspect the files with the widest reach.</p>
        </div>
        <div className="graph-heading-controls">
          <label className="graph-filter"><GitFork size={15} /><input aria-label="Filter graph nodes" placeholder="Filter nodes…" value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
          <label className="test-toggle"><input type="checkbox" checked={includeTests} onChange={(event) => setSearchParams((current) => { const next = new URLSearchParams(current); if (event.target.checked) next.set('include_tests', 'true'); else next.delete('include_tests'); return next })} />Include tests</label>
          <button className="view-toggle" type="button" aria-pressed={searchParams.get('view') === 'list'} onClick={() => setSearchParams((current) => { const next = new URLSearchParams(current); if (next.get('view') === 'list') next.delete('view'); else next.set('view', 'list'); return next })}><Folder size={14} />{searchParams.get('view') === 'list' ? 'Graph view' : 'List view'}</button>
        </div>
      </div>
      <Card className="graph-toolbar">
        <Breadcrumbs path={pathPrefix} repositoryId={repositoryId} />
        <Legend />
      </Card>
      {graph.truncated && <div className="truncated-banner" role="status"><AlertCircle size={15} />Showing the largest 150 of {graph.total_nodes} items</div>}
      {blastQuery.isError && (
        <div className="blast-error" role="alert">
          <AlertCircle size={15} />
          {blastQuery.error instanceof ApiError
            ? `${blastQuery.error.code}: ${blastQuery.error.message}`
            : 'Could not load the blast radius.'}
        </div>
      )}
      {blastQuery.isSuccess && blastFileId && (
        <div className="blast-summary" role="status">
          <GitFork size={15} /><strong>{affectedCount} files affected</strong>
          <button type="button" onClick={() => setBlastFileId(null)} aria-label="Clear blast radius highlight"><X size={14} /> Clear highlight</button>
        </div>
      )}
      {graph.nodes.length === 0 ? (
        <Card><EmptyState title="No modules at this level" description={pathPrefix ? 'This folder has no source files or child folders in the current filter.' : 'No dependency graph data is available for this repository.'} action={pathPrefix ? <button className="text-link" type="button" onClick={() => onPathChange('')}><ArrowLeft size={14} /> Back to all modules</button> : undefined} /></Card>
      ) : searchParams.get('view') === 'list' ? (
        <div className={`graph-layout ${selectedModule ? 'has-details' : ''}`}>
          <Card className="graph-list-card">
            <ModuleList
              nodes={flowData.nodes}
              edges={graph.edges}
              onSelect={onNodeSelect}
              onDrill={onPathChange}
            />
          </Card>
          {selectedModule && (
            <DetailPanel
              selected={selectedModule}
              graph={graph}
              repositoryId={repositoryId}
              onClose={() => setSelectedId(null)}
              onShowBlastRadius={onBlast}
              blastLoading={blastQuery.isFetching}
            />
          )}
        </div>
      ) : (
        <div className={`graph-layout ${selectedModule ? 'has-details' : ''}`}>
          <Card className="graph-card">
            {blastQuery.isSuccess && blastFileId && <div className="affected-count-float"><GitFork size={13} />{affectedCount} files affected</div>}
            <GraphCanvas
              nodes={visibleNodes}
              edges={flowData.edges}
              onNodeClick={onNodeSelect}
              onNodeDrill={onDrill}
              onNodeEnter={setHoveredNode}
              onNodeLeave={() => setHoveredNode(null)}
              onEdgeEnter={setHoveredEdge}
              onEdgeLeave={() => setHoveredEdge(null)}
            />
          </Card>
          {selectedModule && (
            <DetailPanel
              selected={selectedModule}
              graph={graph}
              repositoryId={repositoryId}
              onClose={() => setSelectedId(null)}
              onShowBlastRadius={onBlast}
              blastLoading={blastQuery.isFetching}
            />
          )}
        </div>
      )}
    </div>
  )
}
