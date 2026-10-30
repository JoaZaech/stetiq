"""The read-only web UI (ticket #18): server-rendered HTML, no JavaScript, no build step.

Mounted by `server.create_app` under `/ui`. It reads the same `TrackingService` the
REST API wraps and never changes anything.

Authentication: the UI needs the same API Token as the REST API. It is entered once on
`/ui/login`, checked against the `TokenRegistry`, and kept in an HttpOnly,
SameSite=Strict cookie scoped to `/ui`. Every page re-authenticates the cookie (so a
revoked token stops working at once) and needs `read` on the Knowledge Graph it shows;
the index lists only the Knowledge Graphs the token can read. An `Authorization:
Bearer` header is accepted too, for curl and tests.
"""

from __future__ import annotations

from html import escape
from typing import Iterable
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from stetiq.auth import ApiToken, TokenRegistry
from stetiq.client import Client
from stetiq.errors import AuthenticationError, NotFoundError, PermissionDeniedError
from stetiq.tracking import TrackingService

UI_PREFIX = "/ui"
TOKEN_COOKIE = "stetiq_token"


class _LoginRequired(Exception):
    pass


def ui_router(tracking: TrackingService, registry: TokenRegistry) -> APIRouter:
    """The `/ui` pages over `tracking`, authenticated against `registry`."""
    ui = APIRouter(prefix=UI_PREFIX, include_in_schema=False)

    def current_token(request: Request) -> ApiToken:
        value = request.cookies.get(TOKEN_COOKIE)
        scheme, _, bearer = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and bearer.strip():
            value = bearer.strip()
        try:
            return registry.authenticate(value)
        except AuthenticationError:
            raise _LoginRequired from None

    def page(request: Request, render) -> Response:
        """Authenticate, render, and map domain errors to friendly pages."""
        try:
            token = current_token(request)
            title, crumbs, body = render(token)
        except _LoginRequired:
            return RedirectResponse(f"{UI_PREFIX}/login", status_code=303)
        except PermissionDeniedError as e:
            return _html("No access", [], _notice(str(e)), status=403, signed_in=True)
        except NotFoundError as e:
            return _html("Not found", [], _notice(str(e)), status=404, signed_in=True)
        return _html(title, crumbs, body, signed_in=True)

    @ui.get("/login")
    def login_form() -> Response:
        return _html("Sign in", [], _login_form())

    @ui.post("/login")
    async def login(request: Request) -> Response:
        form = parse_qs((await request.body()).decode())
        value = (form.get("token") or [""])[0].strip()
        try:
            registry.authenticate(value)
        except AuthenticationError as e:
            return _html("Sign in", [], _login_form(str(e)), status=401)
        r = RedirectResponse(UI_PREFIX, status_code=303)
        r.set_cookie(
            TOKEN_COOKIE,
            value,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path=UI_PREFIX,
        )
        return r

    @ui.post("/logout")
    def logout() -> Response:
        r = RedirectResponse(f"{UI_PREFIX}/login", status_code=303)
        r.delete_cookie(TOKEN_COOKIE, path=UI_PREFIX)
        return r

    @ui.get("")
    def index(request: Request) -> Response:
        def render(token: ApiToken):
            kgs = [k for k in tracking.list_knowledge_graphs() if token.allows(k.name, "read")]
            if not kgs:
                body = _notice_empty(
                    "No Knowledge Graphs you can read yet. Create one with "
                    "<code>stetiq kg create</code>, or ask for a token with a read grant."
                )
            else:
                items = "".join(_kg_item(k.name, tracking) for k in kgs)
                body = f'<ul class="kgs">{items}</ul>'
            return "Knowledge Graphs", [], f"<h1>Knowledge Graphs</h1>{body}"

        return page(request, render)

    @ui.get("/kg/{name}")
    def knowledge_graph(request: Request, name: str) -> Response:
        def render(token: ApiToken):
            _readable(token, name)
            versions = tracking.list_ontology_versions(name)
            aliases = tracking.list_aliases(name)
            contract = tracking.get_contract_alias(name)
            by_version: dict[int, list[str]] = {}
            for a in aliases:
                by_version.setdefault(a.version, []).append(a.name)
            rows = "".join(
                _version_row(v.number, v.origin, v.created_at, by_version.get(v.number, []), contract)
                for v in reversed(versions)
            )
            body = (
                f"<h1>{_e(name)}</h1>{_tabs(name, 'versions')}"
                f'<p class="lede">Contract Alias: <span class="alias contract">{_e(contract)}</span>. '
                "Construction Runs consume its Ontology Version; Drift is measured against it.</p>"
                f'<h2>Ontology Versions</h2><ol class="rail" reversed>{rows}</ol>'
            )
            return name, [(name, None)], body

        return page(request, render)

    @ui.get("/kg/{name}/runs")
    def runs(request: Request, name: str) -> Response:
        def render(token: ApiToken):
            _readable(token, name)
            all_runs = list(reversed(tracking.list_runs(name)))
            head = f"<h1>{_e(name)}</h1>{_tabs(name, 'runs')}"
            if not all_runs:
                body = _notice_empty(
                    "No Construction Runs yet. Start one with <code>stetiq run</code> "
                    "or <code>client.start_run()</code>."
                )
                return "Construction Runs", [(name, _kg_url(name)), ("Runs", None)], head + body
            metrics = sorted({k for r in all_runs for k in r.metrics})
            metric_heads = "".join(f'<th class="num" scope="col">{_e(m)}</th>' for m in metrics)
            rows = "".join(_run_row(r, metrics) for r in all_runs)
            body = f"""
<form method="get" action="{_e(_kg_url(name, '/runs/compare'))}">
<p class="lede">Tick two or more runs to compare their params and metrics.</p>
<div class="scroll"><table>
<thead><tr><th scope="col">Compare</th><th scope="col">Run</th><th scope="col">Status</th>
<th class="num" scope="col">Ontology Version</th><th class="num" scope="col">Conformance</th>
<th scope="col">Candidate</th><th scope="col">Started</th>{metric_heads}</tr></thead>
<tbody>{rows}</tbody></table></div>
<p><button type="submit">Compare selected runs</button></p>
</form>"""
            return "Construction Runs", [(name, _kg_url(name)), ("Runs", None)], head + body

        return page(request, render)

    @ui.get("/kg/{name}/runs/compare")
    def compare(request: Request, name: str) -> Response:
        def render(token: ApiToken):
            _readable(token, name)
            ids = request.query_params.getlist("run")
            for run_id in ids:
                if tracking.get_run(run_id).knowledge_graph != name:
                    raise NotFoundError(f"Run {run_id!r} is not a Construction Run of {name!r}")
            cmp = Client(service=tracking).compare_runs(ids)
            heads = "".join(f'<th scope="col">{_e(r.id[:8])}</th>' for r in cmp.runs)
            fixed = [
                ("Status", [r.status for r in cmp.runs]),
                ("Ontology Version", [f"v{r.ontology_version}" for r in cmp.runs]),
                ("Conformance", [_score(r.conformance) for r in cmp.runs]),
            ]
            sections = [("Run", fixed), ("Params", list(cmp.params.items())),
                        ("Metrics", [(k, [_num(v) for v in vs]) for k, vs in cmp.metrics.items()])]
            body_rows = ""
            for title, rows in sections:
                if not rows:
                    continue
                body_rows += f'<tr><th colspan="{len(cmp.runs) + 1}" scope="rowgroup">{title}</th></tr>'
                for key, values in rows:
                    cells = "".join(f"<td>{_e(_dash(v))}</td>" for v in values)
                    body_rows += f'<tr><th scope="row">{_e(key)}</th>{cells}</tr>'
            body = (
                f"<h1>Compare Construction Runs</h1>{_tabs(name, 'runs')}"
                f'<div class="scroll"><table><thead><tr><th></th>{heads}</tr></thead>'
                f"<tbody>{body_rows}</tbody></table></div>"
            )
            crumbs = [(name, _kg_url(name)), ("Runs", _kg_url(name, "/runs")), ("Compare", None)]
            return "Compare runs", crumbs, body

        return page(request, render)

    @ui.get("/kg/{name}/diff")
    def diff(request: Request, name: str) -> Response:
        def render(token: ApiToken):
            _readable(token, name)
            sdk = Client(service=tracking)
            numbers = [v.number for v in tracking.list_ontology_versions(name)]
            base = _version_param(request, "base") or sdk.get_contract_version(name).number
            target = _version_param(request, "target") or numbers[-1]
            result = sdk.diff_ontology_versions(name, base, target)
            picker = f"""
<form class="pick" method="get" action="{_e(_kg_url(name, '/diff'))}">
  <label>Base {_version_select('base', numbers, base)}</label>
  <label>Target {_version_select('target', numbers, target)}</label>
  <button type="submit">Show diff</button>
</form>"""
            if not result.changes:
                table = _notice_empty(f"No changes between v{base} and v{target}.")
            else:
                rows = "".join(
                    f'<tr><td class="cls cls-{_e(c.classification)}">{_e(c.classification)}</td>'
                    f"<td>{_e(c.kind)}</td><td>{_e(c.concept)}</td>"
                    f"<td>{_e(c.concept_kind.replace('_', ' '))}</td><td>{_e(c.detail)}</td></tr>"
                    for c in result.changes
                )
                overall = result.classification
                table = (
                    f'<p class="lede">Overall: <span class="cls cls-{_e(overall)}">{_e(overall)}</span>, '
                    f"{len(result.changes)} change{'s' if len(result.changes) != 1 else ''} "
                    f"from v{base} to v{target}.</p>"
                    '<div class="scroll"><table><thead><tr><th scope="col">Classification</th>'
                    '<th scope="col">Change</th><th scope="col">Concept</th><th scope="col">Kind</th>'
                    f'<th scope="col">Detail</th></tr></thead><tbody>{rows}</tbody></table></div>'
                )
            body = f"<h1>{_e(name)}</h1>{_tabs(name, 'diff')}{picker}{table}"
            return "Ontology Diff", [(name, _kg_url(name)), ("Diff", None)], body

        return page(request, render)

    @ui.get("/kg/{name}/drift")
    def drift(request: Request, name: str) -> Response:
        def render(token: ApiToken):
            _readable(token, name)
            events = list(reversed(tracking.list_drift_events(name)))
            head = f"<h1>{_e(name)}</h1>{_tabs(name, 'drift')}"
            if not events:
                body = _notice_empty(
                    "No Drift detected. Schedule <code>stetiq observe</code> to check the "
                    "Graph Source against the Contract Alias between runs."
                )
            else:
                body = "".join(_drift_event(e) for e in events)
            return "Drift", [(name, _kg_url(name)), ("Drift", None)], head + body

        return page(request, render)

    return ui


def _version_param(request: Request, key: str) -> int | None:
    raw = request.query_params.get(key)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise NotFoundError(f"Ontology Version {raw!r} does not exist") from None


def _version_select(field: str, numbers: list[int], selected: int) -> str:
    options = "".join(
        f'<option value="{n}"{" selected" if n == selected else ""}>v{n}</option>' for n in numbers
    )
    return f'<select name="{field}">{options}</select>'


def _drift_event(event) -> str:
    findings = "".join(
        f"<li><strong>{_e(f.kind.replace('_', ' '))}</strong> {_e(f.subject)}"
        + (
            f" ({f.previous_count} to {f.observed_count})"
            if f.previous_count is not None or f.observed_count is not None
            else ""
        )
        + (f' <span class="meta">{_e(f.detail)}</span>' if f.detail else "")
        + "</li>"
        for f in event.findings
    )
    return (
        f'<article class="event"><h2>{_e(_when(event.detected_at))}</h2>'
        f'<p class="meta">Against <span class="alias contract">{_e(event.contract_alias)}</span> '
        f"at v{event.ontology_version}. {len(event.structural)} structural, "
        f"{len(event.statistical)} statistical finding(s).</p><ul>{findings}</ul></article>"
    )


def _dash(value: object) -> str:
    return "—" if value is None else str(value)


def _num(value: float | None) -> str | None:
    return None if value is None else f"{value:g}"


def _score(conformance) -> str | None:
    return None if conformance is None else f"{conformance.score:.0%}"


def _run_row(run, metrics: list[str]) -> str:
    cells = "".join(f'<td class="num">{_e(_dash(_num(run.metrics.get(m))))}</td>' for m in metrics)
    candidate = f"v{run.candidate_version}" if run.candidate_version else None
    return (
        f'<tr><td><input type="checkbox" name="run" value="{_e(run.id)}" '
        f'aria-label="Compare run {_e(run.id[:8])}"></td>'
        f'<td title="{_e(run.id)}">{_e(run.id[:8])}</td>'
        f'<td class="st-{_e(run.status)}">{_e(run.status)}</td>'
        f'<td class="num">v{run.ontology_version}</td>'
        f'<td class="num">{_e(_dash(_score(run.conformance)))}</td>'
        f"<td>{_e(_dash(candidate))}</td><td>{_e(_when(run.started_at))}</td>{cells}</tr>"
    )


def _readable(token: ApiToken, kg: str) -> None:
    token.require(kg, "read")


def _kg_url(name: str, sub: str = "") -> str:
    return f"{UI_PREFIX}/kg/{quote(name, safe='')}{sub}"


def _kg_item(name: str, tracking: TrackingService) -> str:
    versions = tracking.list_ontology_versions(name)
    contract = tracking.get_contract_alias(name)
    try:
        contract_version = f"v{tracking.get_alias(name, contract).version}"
    except NotFoundError:
        contract_version = "none"
    return (
        f'<li><a href="{_e(_kg_url(name))}">{_e(name)}</a>'
        f'<span class="meta">{len(versions)} Ontology Version{"s" if len(versions) != 1 else ""}</span>'
        f'<span class="meta">{_e(contract)} at {_e(contract_version)}</span></li>'
    )


def _tabs(name: str, current: str) -> str:
    tabs = [("versions", "Ontology Versions", ""), ("runs", "Construction Runs", "/runs"),
            ("diff", "Diff", "/diff"), ("drift", "Drift", "/drift")]
    links = "".join(
        f'<a href="{_e(_kg_url(name, sub))}"{" aria-current=page" if key == current else ""}>{label}</a>'
        for key, label, sub in tabs
    )
    return f'<nav class="tabs" aria-label="Knowledge Graph sections">{links}</nav>'


def _version_row(number, origin, created_at, aliases, contract) -> str:
    pills = "".join(
        f'<span class="alias{" contract" if a == contract else ""}">{_e(a)}</span>'
        for a in sorted(aliases)
    )
    cls = ' class="contract"' if contract in aliases else ""
    return (
        f'<li id="v{number}"{cls}><span class="vnum">v{number}</span>{pills}'
        f'<span class="meta">{_e(origin)} {_e(_when(created_at))}</span></li>'
    )


def _when(moment) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC") if moment else ""


# --- HTML -----------------------------------------------------------------------------


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _notice(message: str) -> str:
    return f'<p class="notice">{_e(message)}</p>'


def _notice_empty(html_message: str) -> str:
    return f'<p class="empty">{html_message}</p>'


def _login_form(error: str | None = None) -> str:
    err = f'<p class="notice" role="alert">{_e(error)}</p>' if error else ""
    return f"""
<section class="login">
  <h1>Sign in to stetiq</h1>
  <p class="lede">Paste an API token with read access. Ask your admin for one
  (<code>stetiq token create USER --grant KG=read</code>).</p>
  {err}
  <form method="post" action="{UI_PREFIX}/login">
    <label for="token">API token</label>
    <input id="token" name="token" type="password" autocomplete="off" required
           placeholder="stq_…">
    <button type="submit">Sign in</button>
  </form>
</section>"""


def _html(
    title: str,
    crumbs: Iterable[tuple[str, str | None]],
    body: str,
    *,
    status: int = 200,
    signed_in: bool = False,
) -> HTMLResponse:
    trail = "".join(
        f'<li><a href="{_e(href)}">{_e(label)}</a></li>' if href else f"<li>{_e(label)}</li>"
        for label, href in crumbs
    )
    logout = (
        f'<form method="post" action="{UI_PREFIX}/logout"><button class="quiet">Sign out</button></form>'
        if signed_in
        else ""
    )
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} | stetiq</title>
<style>{_CSS}</style>
</head>
<body>
<header class="bar">
  <a class="mark" href="{UI_PREFIX}">stetiq</a>
  <ol class="crumbs">{trail}</ol>
  {logout}
</header>
<main>{body}</main>
</body>
</html>"""
    return HTMLResponse(doc, status_code=status)


_CSS = """
:root{--paper:#f2f4f3;--sheet:#fff;--ink:#17232a;--muted:#56666e;--rule:#d3dbd8;
--accent:#1f4f86;--add:#26734a;--dep:#93590a;--brk:#b0281f;--rail:#9fb0ab}
@media (prefers-color-scheme:dark){:root{--paper:#11171a;--sheet:#172025;--ink:#e2e8e6;
--muted:#9aa9a6;--rule:#2a363b;--accent:#8db8ec;--add:#6fcf97;--dep:#e0a85a;--brk:#f08a80;--rail:#4a5b60}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--accent)}a:focus-visible,button:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.bar{display:flex;align-items:center;gap:1rem;padding:.75rem 1rem;border-bottom:1px solid var(--rule);background:var(--sheet)}
.mark{font-weight:700;letter-spacing:-.02em;color:var(--ink);text-decoration:none;font-size:1.05rem}
.crumbs{display:flex;gap:.4rem;list-style:none;margin:0;padding:0;color:var(--muted);flex:1;min-width:0;flex-wrap:wrap}
.crumbs li+li::before{content:"/";margin-right:.4rem;color:var(--rail)}
.bar form{margin:0}
main{max-width:68rem;margin:0 auto;padding:1.5rem 1rem 4rem}
h1{font-size:1.6rem;line-height:1.2;letter-spacing:-.015em;margin:.25rem 0 1rem}
h2{font-size:1.1rem;margin:2rem 0 .5rem}
.lede{color:var(--muted);max-width:60ch}
.notice{border-left:3px solid var(--brk);padding:.5rem .75rem;background:var(--sheet)}
.empty{color:var(--muted)}
button{font:inherit;padding:.45rem .9rem;border:1px solid var(--accent);background:var(--accent);color:var(--sheet);border-radius:4px;cursor:pointer}
button.quiet{background:none;color:var(--muted);border-color:var(--rule)}
input,select{font:inherit;padding:.45rem .6rem;border:1px solid var(--rule);border-radius:4px;background:var(--sheet);color:var(--ink)}
.login{max-width:28rem;margin:3rem auto}.login form{display:grid;gap:.5rem}
code{font-size:.9em}
nav.tabs{display:flex;gap:1.25rem;border-bottom:1px solid var(--rule);margin-bottom:1.25rem;overflow-x:auto}
nav.tabs a{padding:.5rem 0;text-decoration:none;color:var(--muted);border-bottom:2px solid transparent}
nav.tabs a[aria-current=page]{color:var(--ink);border-color:var(--ink)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;background:var(--sheet)}
th,td{text-align:left;padding:.45rem .7rem;border-bottom:1px solid var(--rule);vertical-align:top;white-space:nowrap}
th{font-weight:600;color:var(--muted);font-size:.85rem}
td.num,th.num{text-align:right}
.kgs{list-style:none;padding:0;margin:0;display:grid;gap:.5rem}
.kgs li{background:var(--sheet);border:1px solid var(--rule);padding:.75rem 1rem;display:flex;gap:1rem;flex-wrap:wrap;align-items:baseline}
.kgs a{font-weight:600;font-size:1.05rem}
.meta{color:var(--muted);font-size:.9rem}
.rail{list-style:none;margin:0;padding:0 0 0 1.25rem;border-left:2px solid var(--rail)}
.rail li{position:relative;padding:.6rem 0 .6rem 1rem;display:flex;gap:.9rem;align-items:baseline;flex-wrap:wrap}
.rail li::before{content:"";position:absolute;left:-1.25rem;top:1.05rem;width:.7rem;height:.7rem;margin-left:-.4rem;
border-radius:50%;background:var(--paper);border:2px solid var(--rail)}
.rail li.contract::before{background:var(--accent);border-color:var(--accent)}
.vnum{font-size:1.35rem;font-weight:700;min-width:3ch}
.alias{display:inline-block;padding:.05rem .5rem;border:1px solid var(--accent);color:var(--accent);border-radius:999px;font-size:.85rem}
.alias.contract{background:var(--accent);color:var(--sheet)}
.cls{font-weight:600}.cls-additive{color:var(--add)}.cls-deprecating{color:var(--dep)}.cls-breaking{color:var(--brk)}
.st-failed{color:var(--brk)}.st-finished{color:var(--add)}
form.pick{display:flex;gap:.75rem;align-items:end;flex-wrap:wrap;margin-bottom:1rem}
form.pick label{display:grid;gap:.2rem;font-size:.85rem;color:var(--muted)}
.event{background:var(--sheet);border:1px solid var(--rule);padding:.75rem 1rem;margin-bottom:.75rem}
.event h2{margin:0 0 .25rem;font-size:1rem}
.event ul{margin:.4rem 0 0;padding-left:1.1rem}
"""
