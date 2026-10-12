import { Link, useParams } from 'react-router'

import type { Guide, FileData } from '../api/client'
import { ApiError, api } from '../api/client'
import { useGuide } from '../api/hooks'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, FileCode2, RefreshCw } from 'lucide-react'
import { Card, EmptyState, ErrorState, Skeleton } from '../components/ui'

async function getAllFiles(repositoryId: string): Promise<FileData[]> {
  const first = await api.files(repositoryId, 200, 0)
  const files = [...first.items]
  for (let offset = files.length; offset < first.total; offset += 200) {
    const page = await api.files(repositoryId, 200, offset)
    files.push(...page.items)
  }
  return files
}

export function GuideContent({
  repositoryId,
  guide,
  fileIds,
}: {
  repositoryId: string
  guide: Guide
  fileIds: ReadonlyMap<string, string>
}) {
  const callsTotal = guide.call_counts.reduce((sum, [, count]) => sum + count, 0)
  const entryPoints = new Set(guide.entry_points)
  const imported = new Set(guide.most_imported.map(([path]) => path))
  const fileLink = (path: string) => {
    const fileId = fileIds.get(path)
    return fileId
      ? <Link className="guide-file-link mono" to={`/repositories/${repositoryId}/explorer?file=${encodeURIComponent(fileId)}`}><FileCode2 size={13} />{path}</Link>
      : <span className="mono">{path}</span>
  }

  return (
    <article className="guide-document">
      <header className="guide-cover">
        <span className="eyebrow">ONBOARDING GUIDE</span>
        <h1>Start reading with confidence</h1>
        <p>A practical route through the repository, based on its entry points, imports, and analysis signals.</p>
      </header>
      <section className="guide-section" aria-labelledby="guide-entry-title">
        <div className="guide-section-heading"><BookOpen size={18} /><div><h2 id="guide-entry-title">Entry points</h2><p>Begin with the files that start the application.</p></div></div>
        {guide.entry_points.length ? <ul className="guide-file-list">{guide.entry_points.map((path) => <li key={path}>{fileLink(path)}</li>)}</ul> : <p className="guide-muted">No entry points were detected.</p>}
      </section>
      <section className="guide-section" aria-labelledby="guide-reading-title">
        <div className="guide-section-heading"><ArrowRight size={18} /><div><h2 id="guide-reading-title">Suggested reading order</h2><p>Follow the flow from entry points into the modules they use.</p></div></div>
        {guide.reading_order.length ? (
          <ol className="guide-reading-list">
            {guide.reading_order.map((path, index) => (
              <li key={`${index}:${path}`}>
                <span className="guide-step">{String(index + 1).padStart(2, '0')}</span>
                <div>{fileLink(path)}<p>{entryPoints.has(path) ? 'Application entry point' : imported.has(path) ? 'Frequently imported dependency' : 'Reachable from an entry point'}</p></div>
              </li>
            ))}
          </ol>
        ) : <p className="guide-muted">No reading order is available yet.</p>}
      </section>
      <section className="guide-section" aria-labelledby="guide-imported-title">
        <div className="guide-section-heading"><FileCode2 size={18} /><div><h2 id="guide-imported-title">Most-imported files</h2><p>Shared dependencies that connect multiple parts of the codebase.</p></div></div>
        {guide.most_imported.length ? <ol className="guide-ranked-list">{guide.most_imported.map(([path, count]) => <li key={path}>{fileLink(path)}<span>{count} importers</span></li>)}</ol> : <p className="guide-muted">No internal imports were found.</p>}
      </section>
      <section className="guide-section" aria-labelledby="guide-folder-title">
        <div className="guide-section-heading"><BookOpen size={18} /><div><h2 id="guide-folder-title">Folder summary</h2><p>Analyzed files grouped by top-level directory.</p></div></div>
        {guide.folder_counts.length ? <div className="guide-folder-grid">{guide.folder_counts.map(([name, count]) => <div key={name}><strong>{name}</strong><span>{count} {count === 1 ? 'file' : 'files'}</span></div>)}</div> : <p className="guide-muted">No folders were analyzed.</p>}
      </section>
      <section className="guide-section" aria-labelledby="guide-cycle-title">
        <div className="guide-section-heading"><RefreshCw size={18} /><div><h2 id="guide-cycle-title">Circular imports</h2><p>Cycles can make module initialization harder to follow.</p></div><span className="guide-section-count">{guide.cycles.length}</span></div>
        {guide.cycles.length ? <ul className="guide-cycle-list">{guide.cycles.map((cycle, index) => <li key={`${index}:${cycle.join('|')}`}>{cycle.map((path, pathIndex) => <span key={`${pathIndex}:${path}`}>{fileLink(path)}{pathIndex < cycle.length - 1 && <span className="guide-cycle-arrow">→</span>}</span>)}</li>)}</ul> : <p className="guide-muted">No circular imports detected.</p>}
      </section>
      <section className="guide-section guide-quality" aria-labelledby="guide-quality-title">
        <div className="guide-section-heading"><BookOpen size={18} /><div><h2 id="guide-quality-title">Analysis quality</h2><p>Static call relationships and resolution confidence.</p></div></div>
        <div className="guide-quality-grid">
          {guide.call_counts.map(([confidence, count]) => <div key={confidence}><span>{confidence}</span><strong>{count}</strong></div>)}
          <div><span>Resolution rate</span><strong>{callsTotal ? `${Math.round(guide.resolution_rate * 100)}%` : 'n/a'}</strong></div>
        </div>
        <p className="analysis-note">Dynamic calls are not guessed.</p>
      </section>
    </article>
  )
}

export default function GuidePage() {
  const { repositoryId = '' } = useParams()
  const guideQuery = useGuide(repositoryId)
  const filesQuery = useQuery({
    queryKey: ['repositories', repositoryId, 'guide-files'],
    queryFn: () => getAllFiles(repositoryId),
    enabled: Boolean(repositoryId),
    staleTime: Infinity,
  })
  if (guideQuery.isLoading || filesQuery.isLoading) return <div className="page-wrap"><Skeleton lines={9} /></div>
  const error = guideQuery.error ?? filesQuery.error
  if (error instanceof ApiError && error.status === 409) {
    return <div className="page-wrap"><Card><EmptyState title="Analysis is still running" description="The onboarding guide will be available when repository analysis completes." /></Card></div>
  }
  if (error) return <div className="page-wrap"><ErrorState error={error} /></div>
  if (!guideQuery.data || !filesQuery.data) return null
  const fileIds = new Map(filesQuery.data.map((file) => [file.path, file.id]))
  return <div className="page-wrap"><GuideContent repositoryId={repositoryId} guide={guideQuery.data} fileIds={fileIds} /></div>
}
