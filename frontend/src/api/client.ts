import type { components } from './schema'

export type Repository = components['schemas']['RepositoryResponse']
export type Overview = components['schemas']['OverviewResponse']
export type Problem = components['schemas']['Problem']
export type FileData = components['schemas']['FileResponse']
export type Source = components['schemas']['SourceResponse']
export type Edge = components['schemas']['EdgeResponse']
export type SearchResult = components['schemas']['SearchResponseItem']
export type Graph = components['schemas']['GraphResponse']
export type Guide = components['schemas']['GuideResponse']
export type Page<T> = { items: T[]; total: number }

function queryString(values: Record<string, string | number | boolean | undefined>) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined) query.set(key, String(value))
  }
  const serialized = query.toString()
  return serialized ? `?${serialized}` : ''
}

export class ApiError extends Error {
  readonly code: string
  readonly requestId: string
  readonly status: number

  constructor(problem: Problem, status: number) {
    super(problem.detail)
    this.name = 'ApiError'
    this.code = problem.code
    this.requestId = problem.request_id
    this.status = status
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    const body: unknown = await response.json()
    if (isProblem(body)) throw new ApiError(body, response.status)
    throw new ApiError(
      {
        type: 'about:blank',
        title: 'Request failed',
        status: response.status,
        detail: 'The server returned an unexpected error.',
        code: 'unknown_error',
        request_id: response.headers.get('X-Request-ID') ?? '',
      },
      response.status,
    )
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function isProblem(value: unknown): value is Problem {
  if (typeof value !== 'object' || value === null) return false
  return (
    'code' in value &&
    typeof value.code === 'string' &&
    'detail' in value &&
    typeof value.detail === 'string' &&
    'request_id' in value &&
    typeof value.request_id === 'string' &&
    'title' in value &&
    typeof value.title === 'string' &&
    'type' in value &&
    typeof value.type === 'string' &&
    'status' in value &&
    typeof value.status === 'number'
  )
}

export const api = {
  repositories: () => request<Repository[]>('/api/v1/repositories'),
  repository: (id: string) =>
    request<Repository>(`/api/v1/repositories/${encodeURIComponent(id)}`),
  files: (id: string, limit = 50, offset = 0) =>
    request<Page<FileData>>(
      `/api/v1/repositories/${encodeURIComponent(id)}/files${queryString({ limit, offset })}`,
    ),
  file: (id: string, fileId: string) =>
    request<FileData>(
      `/api/v1/repositories/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}`,
    ),
  source: (id: string, fileId: string) =>
    request<Source>(
      `/api/v1/repositories/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}/source`,
    ),
  fileRelations: (
    id: string,
    fileId: string,
    relation: 'dependents' | 'dependencies',
    options: { transitive?: boolean; depth?: number; limit?: number; offset?: number } = {},
  ) =>
    request<Page<FileData>>(
      `/api/v1/repositories/${encodeURIComponent(id)}/files/${encodeURIComponent(fileId)}/${relation}${queryString({
        transitive: options.transitive,
        depth: options.depth ?? 1,
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
      })}`,
    ),
  symbolEdges: (
    id: string,
    symbolId: string,
    relation: 'usages' | 'callers' | 'callees',
    limit = 50,
    offset = 0,
  ) =>
    request<Page<Edge>>(
      `/api/v1/repositories/${encodeURIComponent(id)}/symbols/${encodeURIComponent(symbolId)}/${relation}${queryString({ limit, offset })}`,
    ),
  search: (id: string, q: string, limit = 50, offset = 0) =>
    request<Page<SearchResult>>(
      `/api/v1/repositories/${encodeURIComponent(id)}/search${queryString({ q, limit, offset })}`,
    ),
  createRepository: (path: string, name: string) =>
    request<Repository>('/api/v1/repositories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, name }),
    }),
  deleteRepository: (id: string) =>
    request<void>(`/api/v1/repositories/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  overview: (id: string) =>
    request<Overview>(`/api/v1/repositories/${encodeURIComponent(id)}/overview`),
  graph: (id: string, maxNodes = 150) =>
    request<Graph>(
      `/api/v1/repositories/${encodeURIComponent(id)}/graph${queryString({ max_nodes: maxNodes })}`,
    ),
  guide: (id: string) =>
    request<Guide>(`/api/v1/repositories/${encodeURIComponent(id)}/guide`),
}
