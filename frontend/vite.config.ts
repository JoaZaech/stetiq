/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, searchForWorkspaceRoot } from 'vite'

// The Python package's version, shown in the sidebar. The build ships inside that
// same package, so pyproject.toml is the single source of truth.
const pyproject = readFileSync(new URL('../pyproject.toml', import.meta.url), 'utf8')
const version = /^version\s*=\s*"([^"]+)"/m.exec(pyproject)?.[1] ?? 'dev'

export default defineConfig({
  // `stetiq server` and `stetiq ui` serve the app at /ui (src/stetiq/ui.py).
  base: '/ui/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  define: { __STETIQ_VERSION__: JSON.stringify(version) },
  build: {
    // Built straight into the Python package, so the wheel ships it.
    outDir: '../src/stetiq/_frontend',
    emptyOutDir: true,
  },
  server: {
    // `npm run dev` proxies the API to a running `stetiq ui` (default port 5000).
    proxy: { '/api': 'http://127.0.0.1:5000' },
    // The user guide lives outside frontend/, in docs/guide (ADR 0004).
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), '../docs/guide'] },
  },
  test: {
    // Vitest covers pure logic only; pages are tested in the browser by Playwright.
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
