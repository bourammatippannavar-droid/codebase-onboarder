import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import type { Guide } from '../api/client'
import { GuideContent } from './GuidePage'

const guide: Guide = {
  entry_points: ['src/main.py'],
  most_imported: [['src/shared.py', 3]],
  reading_order: ['src/main.py', 'src/shared.py'],
  cycles: [['src/a.py', 'src/b.py']],
  folder_counts: [['src', 4]],
  call_counts: [['exact', 2], ['inferred', 1], ['unresolved', 1]],
  not_stored: [],
  resolution_rate: 0.75,
}

describe('onboarding guide', () => {
  it('renders reading sections, linked file mentions, call quality and cycles', () => {
    render(
      <MemoryRouter>
        <GuideContent
          repositoryId="repo-1"
          guide={guide}
          fileIds={new Map([['src/main.py', 'file-1'], ['src/shared.py', 'file-2']])}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: 'Suggested reading order' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Circular imports' })).toBeTruthy()
    expect(screen.getByText('75%')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /src\/main\.py/ })[0]?.getAttribute('href')).toBe(
      '/repositories/repo-1/explorer?file=file-1',
    )
    expect(screen.getByText('Application entry point')).toBeTruthy()
  })

  it('renders empty cycle and call-quality states without raw markup', () => {
    render(
      <MemoryRouter>
        <GuideContent
          repositoryId="repo-1"
          guide={{ ...guide, cycles: [], call_counts: [['exact', 0], ['inferred', 0], ['unresolved', 0]] }}
          fileIds={new Map()}
        />
      </MemoryRouter>,
    )
    expect(screen.getByText('No circular imports detected.')).toBeTruthy()
    expect(screen.getByText('n/a')).toBeTruthy()
  })
})
