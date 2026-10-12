import dagre from '@dagrejs/dagre'
import {
  MarkerType,
  Position,
} from '@xyflow/react'
import type { Edge, Node } from '@xyflow/react'

import type { ModuleEdge, ModuleGraph, ModuleNode } from '../api/client'

export type FlowNodeData = {
  module: ModuleNode
  selected: boolean
  dimmed: boolean
  neighbor: boolean
}

export type FlowEdgeData = {
  count: number
  inCycle: boolean
  hovered: boolean
  dimmed: boolean
}

export type FlowNode = Node<FlowNodeData, 'module'>
export type FlowEdge = Edge<FlowEdgeData, 'module'>

export type FlowState = {
  selectedId?: string | null
  filter?: string
  neighborIds?: ReadonlySet<string>
  affectedFileIds?: ReadonlySet<string>
  affectedPaths?: ReadonlySet<string>
  hoveredEdgeId?: string | null
}

const nodeWidth = 224

function nodeHeight(node: ModuleNode): number {
  return node.kind === 'folder' ? 102 : 94
}

function edgeId(edge: ModuleEdge): string {
  return `${edge.source}=>${edge.target}`
}

export function buildFlow(
  graph: ModuleGraph,
  state: FlowState = {},
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const filter = state.filter?.trim().toLocaleLowerCase() ?? ''
  const nodes: FlowNode[] = graph.nodes.map((module) => {
    const hasMatch =
      !filter ||
      module.path.toLocaleLowerCase().includes(filter) ||
      module.name.toLocaleLowerCase().includes(filter)
    const isAffected = !state.affectedFileIds
      || (module.kind === 'file' && state.affectedFileIds.has(module.file_id))
      || (module.kind !== 'file' && [...(state.affectedPaths ?? [])].some((path) =>
        path === module.path ||
        (module.path === '(root)' ? !path.includes('/') : path.startsWith(`${module.path}/`)),
      ))
    return {
      id: module.id,
      type: 'module',
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        module,
        selected: module.id === state.selectedId,
        dimmed: !hasMatch || !isAffected,
        neighbor: state.neighborIds?.has(module.id) ?? false,
      },
    }
  })
  const edges: FlowEdge[] = graph.edges.map((moduleEdge) => ({
    id: edgeId(moduleEdge),
    type: 'module',
    source: moduleEdge.source,
    target: moduleEdge.target,
    markerEnd: { type: MarkerType.ArrowClosed },
    data: {
      count: moduleEdge.count,
      inCycle: moduleEdge.in_cycle,
      hovered: edgeId(moduleEdge) === state.hoveredEdgeId,
      dimmed:
        nodes.find((node) => node.id === moduleEdge.source)?.data.dimmed === true ||
        nodes.find((node) => node.id === moduleEdge.target)?.data.dimmed === true,
    },
  }))
  return { nodes, edges }
}

export function layoutFlow(
  nodes: FlowNode[],
  edges: FlowEdge[],
  direction: 'LR' | 'TB' = 'LR',
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const graph = new dagre.graphlib.Graph()
  graph.setDefaultEdgeLabel(() => ({}))
  graph.setGraph({
    rankdir: direction,
    nodesep: 42,
    ranksep: 82,
    marginx: 24,
    marginy: 24,
  })
  for (const node of nodes) {
    graph.setNode(node.id, {
      width: nodeWidth,
      height: nodeHeight(node.data.module),
    })
  }
  for (const edge of edges) graph.setEdge(edge.source, edge.target)
  dagre.layout(graph)
  const positioned = nodes.map((node) => {
    const point = graph.node(node.id) as { x: number; y: number }
    const height = nodeHeight(node.data.module)
    return {
      ...node,
      position: { x: point.x - nodeWidth / 2, y: point.y - height / 2 },
    }
  })
  return { nodes: positioned, edges: [...edges] }
}
