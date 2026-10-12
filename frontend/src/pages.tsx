import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  AlertCircle,
  ArrowDownRight,
  ArrowRight,
  Check,
  FileCode2,
  Folder,
  Gauge,
  Plus,
  RefreshCw,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router'

import { ApiError } from './api/client'
import type { Overview, Repository } from './api/client'
import {
  useCreateRepository,
  useDeleteRepository,
  useOverview,
  useRepositories,
} from './api/hooks'
import { Badge, Button, Card, ConfidenceBadge, EmptyState, ErrorState, Skeleton, AnimatedNumber } from './components/ui'

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value))
}

function StatusBadge({ status }: { status: string }) {
  const tone = status === 'ready' ? 'good' : status === 'failed' ? 'bad' : 'info'
  const icon =
    status === 'ready' ? <Check size={12} /> : status === 'failed' ? <AlertCircle size={12} /> : <RefreshCw size={12} />
  return <Badge tone={tone}><span className="badge-content">{icon}{status}</span></Badge>
}

function RepositoryCard({
  repository,
  onDelete,
}: {
  repository: Repository
  onDelete: (repository: Repository) => void
}) {
  const busy = ['pending', 'running'].includes(repository.status)
  return (
    <Card className="repo-card">
      <div className="repo-card-top">
        <span className="repo-card-icon"><Folder size={18} /></span>
        <StatusBadge status={repository.status} />
        {!busy && (
          <button
            className="icon-button delete-button"
            type="button"
            aria-label={`Delete ${repository.name}`}
            onClick={() => onDelete(repository)}
          ><Trash2 size={16} /></button>
        )}
      </div>
      <h2>{repository.name}</h2>
      <p className="mono repo-path">{repository.path}</p>
      {busy ? (
        <div className="progress-block" role="status">
          <div className="progress-track"><span /></div>
          <span>{repository.status === 'pending' ? 'Waiting for analysis' : 'Analyzing source files'}</span>
        </div>
      ) : repository.status === 'ready' ? (
        <>
          <div className="repo-stats">
            <span><FileCode2 size={14} /> {repository.stats.files ?? 0} files</span>
            <span><Gauge size={14} /> {repository.stats.symbols ?? 0} symbols</span>
          </div>
          <div className="repo-card-footer">
            <span>Analyzed {formatTime(repository.finished_at ?? repository.created_at)}</span>
            <Link className="text-link" to={`/repositories/${repository.id}/overview`}>Open <ArrowRight size={14} /></Link>
          </div>
        </>
      ) : (
        <div className="failed-info" role="status">
          <AlertCircle size={14} /><span>{repository.error ?? 'Analysis failed'}</span>
        </div>
      )}
    </Card>
  )
}

export function RepositoriesPage() {
  const { data: repositories, isLoading, error } = useRepositories()
  const create = useCreateRepository()
  const remove = useDeleteRepository()
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [formError, setFormError] = useState('')
  const [deleteError, setDeleteError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    if (!name.trim() || !path.trim()) {
      setFormError('Enter a repository name and path.')
      return
    }
    try {
      await create.mutateAsync({ name: name.trim(), path: path.trim() })
      setName('')
      setPath('')
    } catch (caught) {
      setFormError(caught instanceof ApiError ? `${caught.code}: ${caught.message}` : 'Could not add repository.')
    }
  }

  function deleteRepository(repository: Repository) {
    if (window.confirm(`Delete ${repository.name} and its analysis?`)) {
      setDeleteError('')
      void remove.mutateAsync(repository.id).catch((caught: unknown) => {
        setDeleteError(
          caught instanceof ApiError
            ? `${caught.code}: ${caught.message}`
            : 'Could not delete repository.',
        )
      })
    }
  }

  return (
    <div className="page-wrap">
      <div className="page-heading page-heading-row">
        <div><span className="eyebrow">YOUR WORKSPACES</span><h1>Repositories</h1><p>Map a codebase before you dive in.</p></div>
        <a className="button primary-button" href="#add-repository"><Plus size={16} /> Add repository</a>
      </div>
      {isLoading ? <div className="repo-grid">{Array.from({ length: 3 }, (_, index) => <Card key={index}><Skeleton lines={5} /></Card>)}</div> : error ? <ErrorState error={error} /> : (
        <>
          {deleteError && <div className="form-error" role="alert"><AlertCircle size={15} />{deleteError}</div>}
          {repositories?.length ? (
            <div className="repo-grid">{repositories.map((repository) => <RepositoryCard key={repository.id} repository={repository} onDelete={deleteRepository} />)}</div>
          ) : <Card className="empty-card"><EmptyState title="No repositories yet" description="Add a local codebase to create your first architecture map." /></Card>}
          <Card className="add-card" id="add-repository">
            <div className="section-title"><div className="section-icon"><Plus size={16} /></div><div><h2>Add a repository</h2><p>Analysis runs locally. Your source code stays on this machine.</p></div></div>
            <form className="repo-form" onSubmit={(event) => void submit(event)}>
              <label>Name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. payments-service" /></label>
              <label>Local path<input className="mono" value={path} onChange={(event) => setPath(event.target.value)} placeholder="C:\projects\my-app" /></label>
              {formError && <div className="form-error" role="alert"><AlertCircle size={15} />{formError}</div>}
              <Button className="primary-button" type="submit" disabled={create.isPending}><Plus size={15} />{create.isPending ? 'Adding…' : 'Add repository'}</Button>
            </form>
          </Card>
        </>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  icon,
  suffix,
}: {
  label: string
  value: number
  icon: ReactNode
  suffix?: string
}) {
  return <Card className="metric-card"><div className="metric-label">{icon}{label}</div><div className="metric-value"><AnimatedNumber value={value} />{suffix}</div></Card>
}

export function OverviewContent({
  data,
  onOpenFile,
}: {
  data: Overview
  onOpenFile: (fileId: string) => void
}) {
  const confidence = {
    exact: data.call_confidence.exact ?? 0,
    inferred: data.call_confidence.inferred ?? 0,
    unresolved: data.call_confidence.unresolved ?? 0,
  }
  const callsTotal = confidence.exact + confidence.inferred + confidence.unresolved
  const width = (count: number) => callsTotal ? `${(count / callsTotal) * 100}%` : '0%'
  return (
    <>
      <div className="metric-grid">
        <Metric label="Files analyzed" value={data.files} icon={<FileCode2 size={15} />} />
        <Metric label="Symbols mapped" value={data.symbols} icon={<Gauge size={15} />} />
        <Metric label="Lines of code" value={data.loc} icon={<ArrowDownRight size={15} />} />
        <Metric label="Circular imports" value={data.cycle_count} icon={<RefreshCw size={15} />} />
      </div>
      <div className="overview-grid">
        <Card className="folder-card">
          <div className="section-title"><div><h2>Where the code lives</h2><p>Lines of code by top-level folder</p></div></div>
          {data.folders.length ? <div className="folder-list">{data.folders.map((folder) => {
            const max = Math.max(...data.folders.map((item) => item.loc), 1)
            return <div className="folder-row" key={folder.name}><div className="folder-label"><span>{folder.name}</span><span>{folder.files} files · {folder.loc.toLocaleString()} LOC</span></div><div className="folder-track"><span style={{ width: `${(folder.loc / max) * 100}%` }} /></div></div>
          })}</div> : <p className="muted">No files to display.</p>}
        </Card>
        <Card className="confidence-card">
          <div className="section-title"><div><h2>How sure is the analysis</h2><p>Confidence across call relationships</p></div><span className="resolution-value">{data.resolution_rate === null ? '—' : `${Math.round(data.resolution_rate * 100)}%`}<small>resolved</small></span></div>
          <div className="confidence-bar" aria-label={`Call confidence: ${confidence.exact} exact, ${confidence.inferred} inferred, ${confidence.unresolved} unresolved`}>
            <span className="segment exact" style={{ width: width(confidence.exact) }} />
            <span className="segment inferred" style={{ width: width(confidence.inferred) }} />
            <span className="segment unresolved" style={{ width: width(confidence.unresolved) }} />
          </div>
          <div className="confidence-legend"><ConfidenceBadge value="exact" /><span>{confidence.exact}</span><ConfidenceBadge value="inferred" /><span>{confidence.inferred}</span><ConfidenceBadge value="unresolved" /><span>{confidence.unresolved}</span></div>
          <p className="analysis-note"><ShieldAlert size={14} /> Dynamic calls are not guessed.</p>
        </Card>
      </div>
      <Card className="hotspot-card">
        <div className="section-title section-title-row"><div><h2>Change-risk hotspots</h2><p>Files with the widest dependency reach</p></div><span className="table-count">{data.hotspots.length} files</span></div>
        {data.hotspots.length ? <div className="table-scroll"><table><thead><tr><th>File</th><th>Imported by</th><th>Blast radius</th><th>Lines</th><th>Signals</th></tr></thead><tbody>{data.hotspots.map((hotspot) => <tr key={hotspot.file_id} tabIndex={0} onClick={() => onOpenFile(hotspot.file_id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onOpenFile(hotspot.file_id) }}><td className="mono file-cell"><FileCode2 size={14} />{hotspot.path}</td><td>{hotspot.imported_by}</td><td><span className="risk-number">{hotspot.blast_radius}</span><span className="muted"> files</span></td><td>{hotspot.loc.toLocaleString()}</td><td><span className="flag-list">{hotspot.flags.map((flag) => <Badge key={flag} tone={flag === 'cycle' ? 'bad' : 'warn'}>{flag === 'cycle' ? <RefreshCw size={11} /> : <ShieldAlert size={11} />}{flag}</Badge>)}</span></td></tr>)}</tbody></table></div> : <div className="table-empty">No hotspot data yet.</div>}
      </Card>
      <Card className="reading-card">
        <div className="section-title"><div><h2>Start here</h2><p>A suggested path through this codebase</p></div></div>
        <div className="reading-chips">{data.reading_order.map((item, index) => <button className="reading-chip" key={item.file_id} type="button" onClick={() => onOpenFile(item.file_id)}><span className="reading-index">{String(index + 1).padStart(2, '0')}</span><span className="mono">{item.path}</span><span className="reading-reason">{item.reason}</span><ArrowRight size={14} /></button>)}</div>
      </Card>
    </>
  )
}

export function OverviewPage() {
  const { repositoryId = '' } = useParams()
  const navigate = useNavigate()
  const { data, isLoading, error } = useOverview(repositoryId)
  if (isLoading) return <div className="page-wrap"><Skeleton lines={8} /></div>
  if (error instanceof ApiError && error.status === 409) return <div className="page-wrap"><Card><EmptyState title="Analysis is still running" description="This overview will be ready as soon as the repository analysis completes." action={<Link className="text-link" to="/">Back to repositories <ArrowRight size={14} /></Link>} /></Card></div>
  if (error) return <div className="page-wrap"><ErrorState error={error} /></div>
  if (!data) return null
  return (
    <div className="page-wrap">
      <div className="page-heading page-heading-row"><div><span className="eyebrow">REPOSITORY OVERVIEW</span><h1>Understand the shape of your code</h1><p>Analysis summary, dependency reach, and a sensible place to begin.</p></div><span className="ready-indicator"><span className="connection-dot" /> Analysis ready</span></div>
      <OverviewContent data={data} onOpenFile={(fileId) => navigate(`/repositories/${repositoryId}/explorer/${fileId}`)} />
    </div>
  )
}
