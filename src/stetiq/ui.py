"""Serves the built React frontend (`frontend/`, ADR 0003) at `/ui`.

`npm run build` in `frontend/` writes the production build into `stetiq/_frontend/`,
which ships inside the wheel, so an installed stetiq needs no Node. The app is just
another `/api/v1` client: these routes only hand out static files and do no auth.

Any `/ui` path that is not a built file returns the app shell (`index.html`), so the
client-side router can resolve deep links.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

UI_PREFIX = "/ui"
FRONTEND_DIR = Path(__file__).parent / "_frontend"

_NOT_BUILT = """<!doctype html><title>stetiq</title>
<p>The stetiq web UI has not been built. Run <code>npm ci && npm run build</code>
in <code>frontend/</code>, then restart the server.</p>"""


def ui_router(frontend_dir: Path = FRONTEND_DIR) -> APIRouter:
    """The `/ui` routes over a built frontend in `frontend_dir`."""
    ui = APIRouter(include_in_schema=False)
    root = frontend_dir.resolve()

    def shell() -> Response:
        index = root / "index.html"
        if not index.is_file():
            return HTMLResponse(_NOT_BUILT, status_code=503)
        # The shell names the current hashed assets, so it must never be cached.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    @ui.get("/")
    def home() -> Response:
        return RedirectResponse(UI_PREFIX + "/")

    @ui.get(UI_PREFIX)
    def app_shell() -> Response:
        return shell()

    @ui.get(UI_PREFIX + "/{path:path}")
    def app_file(path: str) -> Response:
        file = (root / path).resolve()
        if path and file.is_relative_to(root) and file.is_file():
            # Vite fingerprints everything under assets/, so it can be cached for good.
            immutable = file.parent == root / "assets"
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if immutable else {}
            return FileResponse(file, headers=headers)
        return shell()

    return ui
