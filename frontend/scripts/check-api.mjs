import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const temporaryDirectory = mkdtempSync(join(tmpdir(), 'onboarder-openapi-'))
const generated = join(temporaryDirectory, 'schema.d.ts')

try {
  execFileSync(
    process.execPath,
    [
      'node_modules/openapi-typescript/bin/cli.js',
      '../backend/openapi.json',
      '-o',
      generated,
    ],
    { stdio: 'inherit' },
  )
  const committed = readFileSync('src/api/schema.d.ts', 'utf8')
  const current = readFileSync(generated, 'utf8')
  if (committed !== current) {
    console.error('Generated API types are stale. Run npm run gen:api.')
    process.exitCode = 1
  } else {
    console.log('Generated API types are up to date.')
  }
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true })
}
