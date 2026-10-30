import { defineConfig, devices } from '@playwright/test'

// Each test starts its own `stetiq ui` (e2e/fixtures.ts), which serves the
// production build from src/stetiq/_frontend: run `npm run build` first.
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
