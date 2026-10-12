import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { MinimumConfidence } from './client'

export const repositoryKeys = {
  all: ['repositories'] as const,
  detail: (id: string) => ['repositories', id] as const,
  files: (id: string, limit: number, offset: number) =>
    ['repositories', id, 'files', limit, offset] as const,
  file: (id: string, fileId: string) => ['repositories', id, 'files', fileId] as const,
  source: (id: string, fileId: string) =>
    ['repositories', id, 'files', fileId, 'source'] as const,
  fileRelations: (
    id: string,
    fileId: string,
    relation: 'dependents' | 'dependencies',
    options: { transitive?: boolean; depth?: number; limit?: number; offset?: number },
  ) => ['repositories', id, 'files', fileId, relation, options] as const,
  tree: (id: string, path: string) => ['repositories', id, 'tree', path] as const,
  symbolEdges: (
    id: string,
    symbolId: string,
    relation: 'usages' | 'callers' | 'callees',
    options: { minConfidence: MinimumConfidence; limit: number; offset: number },
  ) => ['repositories', id, 'symbols', symbolId, relation, options] as const,
  fileImportEdges: (
    id: string,
    fileId: string,
    relation: 'imports' | 'imported-by',
    options: { minConfidence: MinimumConfidence; limit: number; offset: number },
  ) => ['repositories', id, 'files', fileId, 'import-edges', relation, options] as const,
  search: (id: string, q: string, limit: number, offset: number) =>
    ['repositories', id, 'search', q, limit, offset] as const,
  overview: (id: string) => ['repositories', id, 'overview'] as const,
  graph: (id: string, maxNodes: number) => ['repositories', id, 'graph', maxNodes] as const,
  moduleGraph: (id: string, path: string, includeTests: boolean) =>
    ['repositories', id, 'graph', 'modules', path, includeTests] as const,
  guide: (id: string) => ['repositories', id, 'guide'] as const,
}

export function useRepositories() {
  return useQuery({
    queryKey: repositoryKeys.all,
    queryFn: api.repositories,
    refetchInterval: (query) =>
      query.state.data?.some((repository) =>
        ['pending', 'running'].includes(repository.status),
      )
        ? 1500
        : false,
  })
}

export function useRepository(id: string) {
  return useQuery({
    queryKey: repositoryKeys.detail(id),
    queryFn: () => api.repository(id),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useFiles(id: string, limit = 50, offset = 0) {
  return useQuery({
    queryKey: repositoryKeys.files(id, limit, offset),
    queryFn: () => api.files(id, limit, offset),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useFile(id: string, fileId: string) {
  return useQuery({
    queryKey: repositoryKeys.file(id, fileId),
    queryFn: () => api.file(id, fileId),
    enabled: Boolean(id && fileId),
    staleTime: Infinity,
  })
}

export function useSource(id: string, fileId: string) {
  return useQuery({
    queryKey: repositoryKeys.source(id, fileId),
    queryFn: () => api.source(id, fileId),
    enabled: Boolean(id && fileId),
    staleTime: Infinity,
  })
}

export function useFileRelations(
  id: string,
  fileId: string,
  relation: 'dependents' | 'dependencies',
  options: { transitive?: boolean; depth?: number; limit?: number; offset?: number } = {},
) {
  return useQuery({
    queryKey: repositoryKeys.fileRelations(id, fileId, relation, options),
    queryFn: () => api.fileRelations(id, fileId, relation, options),
    enabled: Boolean(id && fileId),
    staleTime: Infinity,
  })
}

export function useTree(id: string, pathPrefix = '') {
  return useQuery({
    queryKey: repositoryKeys.tree(id, pathPrefix),
    queryFn: () => api.tree(id, pathPrefix),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useSymbolEdges(
  id: string,
  symbolId: string,
  relation: 'usages' | 'callers' | 'callees',
  options: {
    minConfidence?: MinimumConfidence
    limit?: number
    offset?: number
  } = {},
) {
  const normalized = {
    minConfidence: options.minConfidence ?? 'inferred',
    limit: options.limit ?? 50,
    offset: options.offset ?? 0,
  }
  return useQuery({
    queryKey: repositoryKeys.symbolEdges(id, symbolId, relation, normalized),
    queryFn: () => api.symbolEdges(id, symbolId, relation, normalized),
    enabled: Boolean(id && symbolId),
    staleTime: Infinity,
  })
}

export function useFileImportEdges(
  id: string,
  fileId: string,
  relation: 'imports' | 'imported-by',
  options: {
    minConfidence?: MinimumConfidence
    limit?: number
    offset?: number
  } = {},
) {
  const normalized = {
    minConfidence: options.minConfidence ?? 'inferred',
    limit: options.limit ?? 50,
    offset: options.offset ?? 0,
  }
  return useQuery({
    queryKey: repositoryKeys.fileImportEdges(id, fileId, relation, normalized),
    queryFn: () => api.fileImportEdges(id, fileId, relation, normalized),
    enabled: Boolean(id && fileId),
    staleTime: Infinity,
  })
}

export function useSearch(id: string, q: string, limit = 50, offset = 0) {
  return useQuery({
    queryKey: repositoryKeys.search(id, q, limit, offset),
    queryFn: () => api.search(id, q, limit, offset),
    enabled: Boolean(id && q.length >= 2),
    staleTime: Infinity,
  })
}

export function useOverview(id: string) {
  return useQuery({
    queryKey: repositoryKeys.overview(id),
    queryFn: () => api.overview(id),
    staleTime: Infinity,
  })
}

export function useGraph(id: string, maxNodes = 150) {
  return useQuery({
    queryKey: repositoryKeys.graph(id, maxNodes),
    queryFn: () => api.graph(id, maxNodes),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useModuleGraph(id: string, pathPrefix = '', includeTests = false) {
  return useQuery({
    queryKey: repositoryKeys.moduleGraph(id, pathPrefix, includeTests),
    queryFn: () => api.moduleGraph(id, pathPrefix, includeTests),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useGuide(id: string) {
  return useQuery({
    queryKey: repositoryKeys.guide(id),
    queryFn: () => api.guide(id),
    enabled: Boolean(id),
    staleTime: Infinity,
  })
}

export function useCreateRepository() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, name }: { path: string; name: string }) =>
      api.createRepository(path, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: repositoryKeys.all }),
  })
}

export function useDeleteRepository() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.deleteRepository,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: repositoryKeys.all }),
  })
}
