import type { SymbolData } from '../api/client'

export type OutlineItem = {
  symbol: SymbolData
  children: OutlineItem[]
}

export function buildSymbolOutline(symbols: readonly SymbolData[]): OutlineItem[] {
  const classes = symbols.filter((symbol) => symbol.kind === 'class')
  const methodsByClass = new Map<string, SymbolData[]>()
  const topLevel: SymbolData[] = []

  for (const symbol of symbols) {
    if (symbol.kind !== 'method') {
      if (symbol.kind !== 'class') topLevel.push(symbol)
      continue
    }
    const parent = classes
      .filter((candidate) => symbol.qualified_name.startsWith(`${candidate.qualified_name}.`))
      .sort((left, right) => right.qualified_name.length - left.qualified_name.length)[0]
    if (!parent) {
      topLevel.push(symbol)
      continue
    }
    const children = methodsByClass.get(parent.id) ?? []
    children.push(symbol)
    methodsByClass.set(parent.id, children)
  }

  const classItems = classes.map((symbol) => ({
    symbol,
    children: (methodsByClass.get(symbol.id) ?? [])
      .sort((left, right) => left.start_line - right.start_line)
      .map((method) => ({ symbol: method, children: [] })),
  }))
  const otherItems = topLevel
    .sort((left, right) => left.start_line - right.start_line)
    .map((symbol) => ({ symbol, children: [] }))
  return [...classItems, ...otherItems].sort(
    (left, right) => left.symbol.start_line - right.symbol.start_line,
  )
}

export function resolveTargetLine(
  requestedLine: number | null | undefined,
  lineCount: number,
): number | null {
  if (requestedLine === null || requestedLine === undefined || lineCount < 1) return null
  return Math.min(Math.max(Math.trunc(requestedLine), 1), lineCount)
}
