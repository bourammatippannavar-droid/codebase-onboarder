import { describe, expect, it } from 'vitest'

import type { ModuleGraph } from '../api/client'
import { buildFlow, layoutFlow } from './flow'

const graph = {
  nodes: [
    {
      id: 'folder-src',
      kind: 'folder',
      name: 'src',
      path: 'src',
      file_count: 2,
      loc: 30,
      in_cycle: false,
    },
    {
      id: 'file-a',
      kind: 'file',
      file_id: 'a',
      name: 'a.py',
      path: 'src/a.py',
      loc: 20,
      imported_by: 3,
      is_entry_point: true,
      in_cycle: true,
      central: false,
    },
    {
      id: 'outside-tests',
      kind: 'outside',
      name: 'tests',
      path: 'tests',
      file_count: 1,
      loc: 8,
      in_cycle: false,
    },
  ],
  edges: [
    { source: 'folder-src', target: 'file-a', count: 2, in_cycle: true },
    { source: 'file-a', target: 'outside-tests', count: 1, in_cycle: false },
  ],
  truncated: false,
  total_nodes: 3,
} satisfies ModuleGraph

describe('buildFlow', () => {
  it('maps file, folder, outside nodes and cycle edges into React Flow data', () => {
    const flow = buildFlow(graph)

    expect(flow.nodes.map((node) => node.data.module.kind)).toEqual([
      'folder',
      'file',
      'outside',
    ])
    expect(flow.edges.map((edge) => edge.data)).toEqual([
      { count: 2, inCycle: true, hovered: false, dimmed: false },
      { count: 1, inCycle: false, hovered: false, dimmed: false },
    ])
  })

  it('dims non-matches and non-affected nodes without changing graph membership', () => {
    const filtered = buildFlow(graph, {
      filter: 'a.py',
      affectedFileIds: new Set(['a']),
    })

    expect(filtered.nodes).toHaveLength(3)
    expect(filtered.nodes.map((node) => node.data.dimmed)).toEqual([
      true,
      false,
      true,
    ])
    expect(filtered.edges.every((edge) => edge.data?.dimmed)).toBe(true)
  })
})

describe('layoutFlow', () => {
  it('assigns distinct, non-overlapping boxes to the fixture graph', () => {
    const source = buildFlow(graph)
    const result = layoutFlow(source.nodes, source.edges)

    expect(result.nodes.map((node) => node.position)).not.toEqual(
      source.nodes.map((node) => node.position),
    )
    for (let left = 0; left < result.nodes.length; left += 1) {
      const first = result.nodes[left]
      if (!first) continue
      const firstHeight = first.data.module.kind === 'folder' ? 102 : 94
      for (let right = left + 1; right < result.nodes.length; right += 1) {
        const second = result.nodes[right]
        if (!second) continue
        const secondHeight = second.data.module.kind === 'folder' ? 102 : 94
        const separated =
          first.position.x + 224 <= second.position.x ||
          second.position.x + 224 <= first.position.x ||
          first.position.y + firstHeight <= second.position.y ||
          second.position.y + secondHeight <= first.position.y
        expect(separated).toBe(true)
      }
    }
  })
})
