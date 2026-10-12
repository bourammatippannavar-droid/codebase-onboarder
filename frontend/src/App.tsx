import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import {
  Activity,
  ArrowRight,
  BookOpen,
  ChevronDown,
  Command,
  FolderTree,
  GitFork,
  Layers3,
  Search,
  Sparkles,
} from 'lucide-react'
import {
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useNavigate,
  useParams,
} from 'react-router'

import { useRepositories } from './api/hooks'
import { OverviewPage, RepositoriesPage } from './pages'
import { Card, EmptyState, ErrorState, Kbd, ThemeToggle } from './components/ui'
import { Skeleton } from './components/ui'
import { CommandPalette } from './command/CommandPalette'

const GraphPage = lazy(() => import('./graph/GraphPage').then((module) => ({ default: module.GraphPage })))
const ExplorerPage = lazy(() => import('./explorer/ExplorerPage'))
const GuidePage = lazy(() => import('./guide/GuidePage'))

class AppErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  override state = { failed: false }

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Application render failure', error.name, info.componentStack)
  }

  override render() {
    return this.state.failed ? (
      <main className="fatal-state">
        <ErrorState error={new Error('The application could not render this page.')} />
      </main>
    ) : (
      this.props.children
    )
  }
}

function Shell() {
  const { data: repositories = [] } = useRepositories()
  const { repositoryId } = useParams()
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const searchButton = useRef<HTMLButtonElement>(null)
  const selected = repositories.find((repository) => repository.id === repositoryId)

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && selected) {
        event.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [selected])

  const closePalette = () => {
    setPaletteOpen(false)
    window.requestAnimationFrame(() => searchButton.current?.focus())
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="Onboarder home">
          <span className="brand-mark"><Layers3 size={19} /></span>
          <span>onboarder<span className="brand-period">.</span></span>
        </Link>
        <label className="sidebar-caption" htmlFor="repository-switcher">Workspace</label>
        <div className="repo-select-wrap">
          <select
            id="repository-switcher"
            className="repo-select"
            aria-label="Repository switcher"
            value={selected?.id ?? ''}
            onChange={(event) => {
              if (event.target.value) navigate(`/repositories/${event.target.value}/overview`)
            }}
          >
            <option value="">All repositories</option>
            {repositories.map((repository) => (
              <option key={repository.id} value={repository.id}>{repository.name}</option>
            ))}
          </select>
          <ChevronDown size={14} aria-hidden="true" />
        </div>
        <p className="sidebar-caption nav-caption">Workspace</p>
        <nav className="side-nav" aria-label="Main navigation">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            <FolderTree size={17} /> Repositories
          </NavLink>
          {selected ? (
            <NavLink
              to={`/repositories/${selected.id}/overview`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <Activity size={17} /> Overview
            </NavLink>
          ) : (
            <span className="nav-link disabled"><Activity size={17} /> Overview</span>
          )}
          {selected ? (
            <NavLink
              to={`/repositories/${selected.id}/graph`}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              <GitFork size={17} /> Graph
            </NavLink>
          ) : (
            <span className="nav-link disabled"><GitFork size={17} /> Graph</span>
          )}
          {selected ? (
            <NavLink to={`/repositories/${selected.id}/explorer`} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Search size={17} /> Explorer
            </NavLink>
          ) : <span className="nav-link disabled"><Search size={17} /> Explorer</span>}
          {selected ? (
            <NavLink to={`/repositories/${selected.id}/guide`} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <BookOpen size={17} /> Guide
            </NavLink>
          ) : <span className="nav-link disabled"><BookOpen size={17} /> Guide</span>}
        </nav>
        <div className="sidebar-bottom">
          <span className="connection-dot" />
          <span>Local analysis</span>
          <span className="version-label">v1.0</span>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> {selected?.name ?? 'Repositories'}</div>
          <div className="topbar-actions">
            <button ref={searchButton} className="search-trigger" type="button" aria-label="Search repository" disabled={!selected} onClick={() => setPaletteOpen(true)}>
              <Search size={15} /><span>Search</span><Kbd><Command size={11} /> K</Kbd>
            </button>
            <ThemeToggle />
            <span className="avatar" aria-label="Local workspace"><Sparkles size={16} /></span>
          </div>
        </header>
        <main className="page-content">
          <Suspense fallback={<div className="page-wrap" aria-label="Loading page"><Skeleton lines={8} /></div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
      {paletteOpen && selected && <CommandPalette repositoryId={selected.id} onClose={closePalette} />}
    </div>
  )
}

function NotFound() {
  return (
    <div className="page-wrap">
      <Card><EmptyState title="Page not found" description="The route does not exist." action={<Link className="text-link" to="/">Back to repositories <ArrowRight size={14} /></Link>} /></Card>
    </div>
  )
}

function RoutedPages() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<RepositoriesPage />} />
        <Route path="repositories/:repositoryId/overview" element={<OverviewPage />} />
        <Route path="repositories/:repositoryId/explorer" element={<ExplorerPage />} />
        <Route path="repositories/:repositoryId/graph" element={<GraphPage />} />
        <Route path="repositories/:repositoryId/guide" element={<GuidePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return <AppErrorBoundary><RoutedPages /></AppErrorBoundary>
}
