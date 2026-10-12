import { useEffect, useRef, useState } from 'react'
import { EditorState } from '@codemirror/state'
import { defaultHighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { python } from '@codemirror/lang-python'
import { Decoration, EditorView, lineNumbers, highlightActiveLine } from '@codemirror/view'

import { resolveTargetLine } from './outline'

const highlightedLine = Decoration.line({ class: 'cm-target-line' })

export function SourceViewer({
  content,
  line,
}: {
  content: string
  line: number | null
}) {
  const host = useRef<HTMLDivElement>(null)
  const [lightTheme, setLightTheme] = useState(
    document.documentElement.dataset.theme === 'light',
  )

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setLightTheme(document.documentElement.dataset.theme === 'light')
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!host.current) return
    const state = EditorState.create({
      doc: content,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        python(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        EditorState.readOnly.of(true),
        EditorView.editable.of(false),
        EditorView.theme(
          {
            '&': { height: '100%', color: 'var(--text)', backgroundColor: 'var(--surface)' },
            '.cm-scroller': { overflow: 'auto', fontFamily: '"JetBrains Mono Variable", monospace' },
            '.cm-content': { caretColor: 'transparent' },
            '.cm-gutters': { color: 'var(--subtle)', backgroundColor: 'var(--surface-soft)', borderRight: '1px solid var(--border)' },
            '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--accent-a) 6%, transparent)' },
            '.cm-activeLineGutter': { color: 'var(--text)', backgroundColor: 'color-mix(in srgb, var(--accent-a) 10%, transparent)' },
            '.cm-target-line': { backgroundColor: 'color-mix(in srgb, var(--amber) 18%, transparent)' },
          },
          { dark: !lightTheme },
        ),
        ...(resolveTargetLine(line, content.split(/\r?\n/).length) === null
          ? []
          : [
              EditorView.decorations.of((view) => {
                const target = resolveTargetLine(line, view.state.doc.lines)
                if (target === null) return Decoration.none
                const from = view.state.doc.line(target).from
                return Decoration.set([highlightedLine.range(from)])
              }),
            ]),
      ],
    })
    const view = new EditorView({ state, parent: host.current })
    const target = resolveTargetLine(line, view.state.doc.lines)
    if (target !== null) {
      const targetPosition = view.state.doc.line(target).from
      view.dispatch({
        effects: EditorView.scrollIntoView(targetPosition, { y: 'center' }),
      })
    }
    return () => view.destroy()
  }, [content, lightTheme, line])

  return <div className="code-viewer-host" ref={host} aria-label="Read-only source code" />
}
