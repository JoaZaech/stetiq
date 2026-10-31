import { defineConfig, devices } from '@playwright/test'

// Each test starts its own `stetiq ui` (e2e/fixtures.ts), which serves the
// production build from src/stetiq/_frontend: run `npm run build` first.
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // Locally, `dot` keeps a green run to a few lines and still prints each failure
  // in full; STETIQ_E2E_LIST=1 brings back one line per test.
  reporter: process.env.CI
    ? [['github'], ['html', { open: 'never' }]]
    : process.env.STETIQ_E2E_LIST
      ? 'list'
      : 'dot',
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
