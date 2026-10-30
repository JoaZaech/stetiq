# The web UI is a React app built into the Python package and served by `stetiq server`

We replaced the server-rendered HTML pages (`web.py`) with a React + TypeScript app (Vite, shadcn/ui on Tailwind, TanStack Table, Recharts) in `frontend/`. The goal is a richer, MLflow-style UI with charts and with governance writes: Promotion, descriptions, and adding or editing Competency Questions. The app reads and writes only through `/api/v1`, like any other client. Its static build is bundled into the wheel and served at `/ui`, so `pip install stetiq` still ships a working UI and only people working on the UI need Node.

## Considered Options

- **Keep server-rendered HTML with a little vanilla JS.** No build step, but charts and interactive editing get painful, and it can't match the MLflow experience we're aiming for.
- **A separately deployed frontend.** Rejected because it needs CORS, a second origin for auth, and a second artifact to version.

## Consequences

- Any data a page needs must exist on `/api/v1`. The UI never calls `TrackingService` directly.
- Sign-in still takes an existing API Token (ADR 0002). It is kept in an HttpOnly, SameSite=Strict cookie that `/api/v1` accepts alongside the Bearer header. Writes authenticated by that cookie need a CSRF check.
- Building a release now needs `npm run build` to run before the Python build.
