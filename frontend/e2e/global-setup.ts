import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { REPO_ROOT } from './fixtures'

/** Fails fast when the app the tests would load has not been built. */
export default function globalSetup() {
  const shell = join(REPO_ROOT, 'src', 'stetiq', '_frontend', 'index.html')
  if (!existsSync(shell)) {
    throw new Error(`${shell} is missing: run \`npm run build\` before the Playwright tests`)
  }
}
