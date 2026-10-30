# Running checks

Checks are quiet when green and print failures in full, so a passing run costs a line or two of context. Don't pipe them through `tail` to save space; a failure needs its whole output.

- **Install** frontend dependencies with `npm ci --silent --no-audit --no-fund` in `frontend/`.
- **Frontend:** `npm run check` in `frontend/` runs typecheck, lint and the unit tests. A green run prints `check passed: typecheck, lint, unit tests`; a failing step prints its full output and the run ends with `check failed: <steps>`.
- **Playwright while building:** run only the specs you touched, e.g. `npx playwright test e2e/help.spec.ts`. Run `npm run build` first, because the tests serve the production build.
- **Playwright before reporting:** run the full suite once with `npm run test:e2e`. Locally it uses the `dot` reporter; set `STETIQ_E2E_LIST=1` for one line per test.
- **Python:** `uv run pytest` is quiet by default (`-q` in `pyproject.toml`). Pass `-v` for one line per test.
