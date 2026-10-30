/**
 * The Playwright harness: every test gets its own real stetiq over a fresh SQLite
 * database, seeded through the Python SDK (see seed.py).
 *
 *   import { test, expect } from './fixtures'
 *   test.use({ seed: 'empty' })
 *   test('...', async ({ page, stetiq }) => { await page.goto('/ui/settings') })
 *
 * By default that is `stetiq ui` (local mode, no tokens). With `mode: 'server'` it is a
 * token-requiring `stetiq server` instead: issue tokens in the seed scenario
 * (`issue_token`) and sign in with `signIn(page, token)`.
 *
 * `baseURL` is the server's origin, so navigate with absolute `/ui/...` paths.
 */
import { type ChildProcess, execFileSync, spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { createServer } from 'node:net'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { type Page, test as base } from '@playwright/test'

export { expect } from '@playwright/test'

export const REPO_ROOT = fileURLToPath(new URL('../..', import.meta.url))
const SEED_SCRIPT = join(REPO_ROOT, 'frontend', 'e2e', 'seed.py')

export interface StetiqApp {
  /** Origin of the running server, e.g. http://127.0.0.1:53123 */
  url: string
  /** The tracking URI the server reads; seed more data with the SDK on it if needed. */
  trackingUri: string
  /** Whatever the seed scenario returned (ids, version numbers, tokens...). */
  seeded: Record<string, unknown>
}

interface Options {
  /** Name of a scenario function in seed.py. */
  seed: string
  /** The local actor `stetiq ui` records actions with ($STETIQ_ACTOR). */
  actor: string
  /** `ui`: `stetiq ui`, no tokens. `server`: `stetiq server`, which requires API Tokens. */
  mode: 'ui' | 'server'
}

export const test = base.extend<Options & { stetiq: StetiqApp }>({
  seed: ['empty', { option: true }],
  actor: ['e2e', { option: true }],
  mode: ['ui', { option: true }],

  stetiq: async ({ seed, actor, mode }, use, testInfo) => {
    const dir = testInfo.outputPath('stetiq')
    mkdirSync(dir, { recursive: true })
    const trackingUri = `sqlite:///${join(dir, 'stetiq.db')}`
    const seeded = JSON.parse(
      execFileSync('uv', ['run', '--frozen', 'python', SEED_SCRIPT, seed, trackingUri], {
        cwd: REPO_ROOT,
        encoding: 'utf8',
      }),
    ) as Record<string, unknown>

    const port = await freePort()
    const command =
      mode === 'server'
        ? ['server', '--database-url', trackingUri]
        : ['ui', '--tracking-uri', trackingUri]
    const server = spawn('uv', ['run', '--frozen', 'stetiq', ...command, '--port', String(port)], {
      cwd: REPO_ROOT,
      env: { ...process.env, STETIQ_ACTOR: actor },
      stdio: 'pipe',
    })
    let log = ''
    server.stdout?.on('data', (chunk: Buffer) => (log += chunk.toString()))
    server.stderr?.on('data', (chunk: Buffer) => (log += chunk.toString()))
    const url = `http://127.0.0.1:${port}`
    try {
      await waitUntilHealthy(url, server, () => log)
      await use({ url, trackingUri, seeded })
    } finally {
      await stop(server)
      await testInfo.attach(`stetiq ${mode} log`, { body: log, contentType: 'text/plain' })
    }
  },

  baseURL: async ({ stetiq }, use) => {
    await use(stetiq.url)
  },
})

/** Signs in to a `mode: 'server'` stetiq by pasting `token` on the sign-in page. */
export async function signIn(page: Page, token: string) {
  await page.goto('/ui/sign-in')
  await page.getByLabel('API Token').fill(token)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((url) => !url.pathname.startsWith('/ui/sign-in'))
}

/** Runs the `stetiq` CLI in the repo's environment, e.g. `stetiqCli('token', 'revoke', id, ...)`. */
export function stetiqCli(...args: string[]): string {
  return execFileSync('uv', ['run', '--frozen', 'stetiq', ...args], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createServer()
    probe.unref()
    probe.on('error', reject)
    probe.listen(0, '127.0.0.1', () => {
      const address = probe.address()
      probe.close(() =>
        typeof address === 'object' && address ? resolve(address.port) : reject(new Error('no port')),
      )
    })
  })
}

async function waitUntilHealthy(url: string, server: ChildProcess, log: () => string) {
  const deadline = Date.now() + 20_000
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new Error(`stetiq exited with ${server.exitCode}:\n${log()}`)
    }
    try {
      if ((await fetch(`${url}/health`)).ok) return
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(`stetiq did not become healthy at ${url}:\n${log()}`)
}

async function stop(server: ChildProcess) {
  if (server.exitCode !== null) return
  const exited = new Promise((r) => server.once('exit', r))
  server.kill('SIGTERM')
  await exited
}
