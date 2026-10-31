# Architecture notes for coding agents

Conventions, reasons and gotchas that the code does not state outright. Terms are from `GLOSSARY.md`. Read the code for signatures and route lists. Each `##`/`###` section stands alone, so a brief can cite one (e.g. *Frontend › Map*, *Testing › End-to-end*) instead of the whole file.

## Layering

`Client` (SDK, `client.py`) → `TrackingService` (Protocol, `tracking/service.py`) → `Store` (Protocol, `tracking/store.py`, implemented by `SqlStore`).

- **`Client`** converts formats (YAML text, a path, or a model to `Ontology`/`UseCase`), composes service calls (`diff_ontology_versions`, `add_competency_question`, `latest_candidate`), and runs the code that has to live in the user's process (see *Where code runs*). It holds no domain rules and resolves no defaults: an argument it was not given, it passes on as `None`.
- **`LocalTrackingService`** holds every domain rule: version dedupe by content hash, per-Knowledge-Graph numbering, `production` → v1 on creation, Conformance and Evolution Mode in `end_run`, built-in Evaluators, Drift, and Gate evaluation. It also owns every default and argument check: an operation takes "not given" (`None`) and resolves it itself (the Contract Alias's version for `start_run`, the latest Use Case Version for `get_use_case_version`, default Drift thresholds, the latest version for `evaluate_gates`), and it raises the `StetiqError` for conflicting arguments. Service methods take and return model/entity values, never YAML.
- **Checks that run twice on purpose.** A check that must also fire before a request leaves the SDK calls the service's own function, so the message is the same in every mode: `check_not_built_in` (custom Evaluators run SDK-side, see *Reserved Evaluator names*), `validate_alias_name` in `RemoteTrackingService.set_alias` (an empty or `/`-containing name never reaches its route) and `check_use_case` in `RemoteTrackingService.register_use_case` (`to_dict` and JSON encoding assume a valid model).
- **`Store`** is persistence only. `transaction()` nests: inner calls join the outer connection, which is held per thread. On Postgres, `get_knowledge_graph` inside a transaction takes `SELECT … FOR UPDATE`, so version numbering is serialised. On SQLite the store emits `BEGIN IMMEDIATE`.
- **The tracking URI picks the mode** (`client.service_for_uri`). `http(s)://` gives remote mode (`RemoteTrackingService`, sending the API Token). `sqlite:///…` or `postgresql[+psycopg]://…` gives local mode (`LocalTrackingService(SqlStore)`, tokenless). Resolution order is the argument, then `$STETIQ_TRACKING_URI`, then `sqlite:///.stetiq/stetiq.db`.
- **The server** (`server.create_app`) wraps a `LocalTrackingService` and adds no rules of its own. It re-validates every incoming body (`parse_dict`, `parse_use_case_dict`, `parse_gates`), because `from_dict` does not validate.
- **Content hashes.** Ontologies and Use Cases hash through `stetiq.digest` (sha256 of the canonical JSON). The Ontology hash is pinned by a golden test in `tests/test_ontology_versions.py`. If you change the canonical form, existing stores stop deduping, so treat it as a migration. New optional model fields must be **omitted from the canonical form when they hold their default**, so that old hashes stay stable. `parent` and `constraints` follow this rule.
- **Schema changes.** `metadata.create_all` adds new tables to old databases. It never alters an existing table, so a column added to a table that has already shipped must also go in `sql_store._ADDED_COLUMNS`. There is no Alembic.

## Adding an operation

Touch every one of these places, in this order:

1. **`TrackingService` Protocol + `LocalTrackingService`.** The domain rule goes here, inside `self._store.transaction()` when the operation writes. Raise a `StetiqError` subclass.
2. **`Store` Protocol + `SqlStore`** if the operation persists something. Add the new tables to `sql_store.metadata`, and the new columns of shipped tables to `_ADDED_COLUMNS`.
3. **`tracking/wire.py`.** Add `*_to_json`/`*_from_json` for each new entity. When you add a field to an existing entity, read it with `.get` and a default so older payloads still parse. A new error class must be defined **in `stetiq/errors.py`** (`error_from_json` looks it up there by name), and its HTTP status set with `ERROR_STATUS[...] = …` next to its entity. The default status is 400.
4. **Server route** in `server.create_app`, under `api` (prefix `/api/v1`). Call `tracking.<method>` and return `wire.*_to_json`. Read the auth rules below first. Don't name a body field `schema`, because it clashes with pydantic; the existing routes use `observed_schema`.
5. **`RemoteTrackingService`** method: `self._call(METHOD, path, body)` → `wire.*_from_json`. Build paths with `_kg_path(name)` and `quote(id, safe='')`.
6. **`Client`** method: format conversion only, then `self._service.<method>`. Pass an argument the caller left out on as `None`; the service resolves the default.
7. **CLI** command in `cli.py`. Catch `StetiqError` and `raise _fail(e)`, which prints `error: …` and exits 1. Every CLI command that touches tracking takes `--tracking-uri` (`TrackingUri`). The token comes only from `$STETIQ_TOKEN`: there is no `--token` flag. Add a smoke test with `CliRunner`, as in `tests/test_cli_local_smoke.py`.
8. **Export** new public names from `stetiq/__init__.py`.
9. **Tests** go through the `client` fixture, so they run in every mode (see *Testing*).
10. **User guide.** Describe the new capability in `docs/guide/` (the SDK, CLI, server or `stetiq.yaml` page it belongs to), so it shows under Help in the web UI (ADR 0004).

An operation that only composes existing service calls belongs in `Client` alone, with no change to the service, wire or server. `diff_ontology_versions`, `diff_ontologies` and `add_competency_question` work this way. Composing is not the same as defaulting: when the composition needs a default (the Contract Alias's version, the latest Use Case Version), it asks the service for it (`get_contract_version`, `get_use_case_version` without a number) rather than working it out itself. The one exception is the web UI, which can only reach `/api/v1` (ADR 0003): a server route may compose existing service calls for it (the Ontology Diff route, the `candidate` flag on the version list), as long as the route adds no domain rule of its own. A rule both the route and `Client` need goes in the service (e.g. `list_candidates`, which `Client.latest_candidate` also uses).

## Server auth for new routes

API Tokens are described in `auth.py` and ADR 0002. A router-level dependency, `authorize`, runs on every `/api/v1` route. `/health` is open.

- **GET/HEAD needs `read`. Every other method needs `edit`.**
- **The target Knowledge Graph comes from path params only.** `{name}` is used directly. `{run_id}` and `{observation_id}` are looked up to find their Knowledge Graph. When a route has both `name` and `run_id`, `name` wins, and the service must check that the run belongs to it (`_check_subject` does this).
- **The check fails closed.** A route that has none of those params returns 403 for everyone. The only exemptions are `POST` and `GET` on `/knowledge-graphs` exactly (POST checks `edit` on the body `name` inside the route, and GET filters with `token.allows(kg, "read")`) and `GET /whoami`, which only describes the token itself. So a new route either uses one of these path params, or adds an exemption and authorizes itself with `request.state.token.require(kg, perm)`.
- **A uniform 404 for ids outside the token's grants.** A `run_id`/`observation_id` whose Knowledge Graph the token cannot read gets the same NotFound as an unknown id, so ids never reveal what exists. A new id-keyed path param must be added to `lookups` in `_target_knowledge_graph` so it behaves the same way. A `{name}` route answers 403 for a Knowledge Graph outside the grants (the name is already in the URL, so a 404 would hide nothing); its unknown versions or other sub-resources stay 404.
- **Actor.** Any server-side audit entry records `request.state.token.user` and ignores whatever actor the body carries. `set_alias` still accepts an optional body `actor` for wire compatibility and drops it; the web UI sends none. In local mode, `Client.actor` is recorded instead (the argument, then `$STETIQ_ACTOR`, then the OS user).
- **Local mode (`stetiq ui`).** `create_app(local_actor=…)` turns authentication off: `authorize` still runs, but over a synthetic token for `local_actor` with `{"*": "edit"}`, so the rules above and the actor recording work unchanged. `stetiq ui` resolves the tracking URI like every CLI command, refuses an `http(s)://` one, and refuses a non-loopback `--host` unless `--no-auth` is passed.
- **Web UI sign-in.** `POST /auth/sign-in` (outside `/api/v1`, so `authorize` does not run) checks a pasted API Token and sets two cookies, both `SameSite=Strict`, `Path=/`, and `Secure` over https: the HttpOnly `stetiq_token` and a readable `stetiq_csrf`. `POST /auth/sign-out` deletes both. `authenticate` takes the Bearer header first and the cookie otherwise, so the permission rules above apply unchanged. A cookie-authenticated request that is not GET/HEAD must also send `X-CSRF-Token` equal to the `stetiq_csrf` cookie (double-submit, `auth.check_csrf`), or it gets a 403; Bearer requests are exempt, because other sites cannot make a browser send that header. Under `stetiq ui` there is nothing to sign in to, and sign-in returns 400.
- **Web UI.** `/ui` (`ui.py`) serves the React build from `stetiq/_frontend` (ADR 0003) and does no auth: the app is just another `/api/v1` client. Any `/ui` path that is not a built file returns `index.html`, so deep links work. Pages, the release build and the user guide are under *Frontend*.

## Where code runs

The rule: **user code and graph credentials stay in the SDK process, and the server is the authority for verdicts and provenance.** In remote mode the server never connects to the graph database.

These run **in the SDK process**:
- Graph Source **Observation**. `ActiveRun.end()` and `Client.observe()` call `adapter.observe(scope)` and send `(scope, ObservedSchema)` to the service. The adapter comes from `Client(graph_source=…)`, otherwise it is built lazily by `graph_source_from_env()` (`STETIQ_GRAPH_SOURCE_URI`/`_USER`/`_PASSWORD`). Credentials are never sent to the service or persisted; only the scope is bound. Only aggregates leave the process (ADR 0001).
- **Custom Evaluators** (`Client.register_evaluator`, the one-off `evaluators=`). Registration lasts for the life of the `Client` and is not persisted. Only their results are sent, via `record_evaluation`. A failing Evaluator raises `EvaluatorError` after the version or run already exists.
- **Executed Competency Questions** (`competency_question_execution`), through `ScopedGraphSource.execute_read`. Rows are judged and then dropped. An error records only the exception type name, because database messages can quote values.
- `GoldOntologyAlignment` (client-side, parameterised).

These run **in the tracking service**, which is server-side in remote mode:
- The version built-ins (`BUILT_IN_EVALUATORS`) and `structural_answerability` run in `_register` for every *new* version, Candidates included. A dedupe hit does not re-run them.
- `structural_answerability` also runs in `register_use_case` for every *new* Use Case Version, against the **latest** Ontology Version only, in the same transaction. The other built-ins are not re-run, and a dedupe hit judges nothing. This is why the web UI never calls `POST …/evaluate` after saving a Use Case: it only reads the stored result.
- Conformance, the Evolution Mode decision, Candidate registration (`origin="run"`) and the run built-ins `conformance` and `observed_schema` all run in `end_run`, in one transaction.
- Drift (`record_observation`). It never registers a version or moves an Alias.
- **Gates.** The client sends Gate *definitions* only (`POST …/gate-results`). The server gathers the inputs, computes the outcomes and records them, and the Promotion audit's `gate_result` column reads that record.
- The question mapper (`LocalTrackingService(question_mapper=…)`, `stetiq server --question-mapper` / `$STETIQ_QUESTION_MAPPER`). In remote mode the client's env var has no effect. Mapper exceptions turn the question into `unmapped` with `data.error`, so versioning is never blocked.

Origin is decided by the server: `register_ontology` has no `origin` argument, and versions with origin `"run"` only come from `end_run`. `tests/test_server_trust.py` pins what the server refuses to take on the client's word. Extend it when you add a server-computed fact.

`SubjectKind` (`evaluation/framework.py`: `ontology_version` | `construction_run`) is the single subject type, used by evaluation results and Gate results. `ConceptKind` (`ontology/model.py`) is shared by Diff, Conformance and Drift. Reuse both rather than defining new literals.

## Reserved Evaluator names

`RESERVED_EVALUATOR_NAMES` (`tracking/service.py`) is the union of the version built-ins (`hierarchy`, `isolated_node_types`, `orphan_concepts`, `redundancy`, `constraint_consistency`), `structural_answerability`, and the run Evaluators `conformance`, `observed_schema` and `competency_question_execution`.

- `Client.register_evaluator` and the one-off `evaluators=` reject these names, before running anything, through the service's `check_not_built_in`, so the message is the same as the service's. `record_evaluation` refuses them too, with one exception: `competency_question_execution` is accepted on a `construction_run` subject, because it is a built-in that has to run on the SDK side.
- Gates name these Evaluators and their metrics in users' `stetiq.yaml`, so **renaming one is a breaking change**. A new built-in must be added to this set.
- `get_evaluation_results` returns the latest result per (evaluator, parameters), so an evaluator name can appear more than once in the list.

## Repo config (`stetiq.yaml`)

`config.load_config(path)` returns the raw mapping and ignores unknown top-level keys. Each feature parses only its own section, in its own module, and raises its own `StetiqError`+`ValueError` subclass (422).

| Section | Parsed by | Used by |
|---|---|---|
| `knowledge_graph:` | CLI | the default Knowledge Graph for `run`, `observe` and `gate` |
| `entry_point: {command}` | `EntryPoint.from_config` | `stetiq run` (a string is `shlex.split` and run with no shell; a list is used as-is) |
| `gates:` | `gates.parse_gates` | `stetiq gate` |
| `drift: {max_count_drop, max_count_increase}` | `drift.thresholds_from_config` | `stetiq observe` |

A new section gets its own parser module. Don't grow `config.py`.

Exit codes are a contract with CI and schedulers:
- `stetiq gate`: **0** means all Gates passed, **3** means a Gate failed (`GATE_FAILED_EXIT_CODE`), **1** means an error (missing or bad config, no Gates, unknown Knowledge Graph or version).
- `stetiq observe`: **0** means no Drift, **3** means Drift (`DRIFT_EXIT_CODE`), **1** means an error. A missing *default* `./stetiq.yaml` counts as an empty config. A missing `--config` file is an error.
- `stetiq run`: **1** whenever the run's status is not `finished`, which includes a strict Evolution Mode failure. The SDK never raises in that case, so callers must check `status`.
- Every other command exits 1 on a `StetiqError`. Typer usage errors exit 2.

## Frontend

The web UI is a React app in `frontend/` (ADR 0003), served at `/ui` (see *Server auth › Web UI*). It reaches the server only through `/api/v1`.

| Folder | Holds |
|---|---|
| `src/app/` | the shell: `router.tsx` (every page is registered here), `AppLayout`, the sidebar and Knowledge Graph switcher, breadcrumbs |
| `src/api/` | one module per `/api/v1` resource, plus `client.ts` and `session.ts` |
| `src/components/` | shared components (`components/ui/` is the shadcn base) |
| `src/lib/`, `src/hooks/`, `src/theme/` | framework-free helpers, React hooks, the theme |
| `src/pages/<area>/` | one folder per page area: `home`, `knowledge-graphs`, `knowledge-graph`, `settings`, `sign-in`, `help` |
| `src/pages/knowledge-graph/versions/` | the Ontology Version pages; the Map, Table and Comparison have their own folders, below |
| `e2e/` | the Playwright specs, harness and seeds (see *Testing › End-to-end*) |

### Map

The Ontology Map, a node-link view of an Ontology Version. See [`versions/map/README.md`](../frontend/src/pages/knowledge-graph/versions/map/README.md).

### Table

The Ontology tab's Table view and its links to the Map. See [`versions/table/README.md`](../frontend/src/pages/knowledge-graph/versions/table/README.md).

### Comparison

Comparing two Ontology Versions, as a Map or a Table. See [`versions/comparison/README.md`](../frontend/src/pages/knowledge-graph/versions/comparison/README.md).

### Build and release

A release must run `npm run build` in `frontend/` before `uv build`: the wheel only ships what is in `src/stetiq/_frontend` (gitignored), and `tests/test_packaging.py` fails under `CI` when it is missing.

### User guide

The Markdown files in `docs/guide/` are bundled into the web UI at build time (ADR 0004) and shown at `/ui/help/:page`. `frontend/src/pages/help/guide-index.ts` orders them by number prefix and takes each page's slug from its filename and its title from its first `#` heading, so a new page is just a new numbered file. Link between pages with relative `.md` links (`./04-cli.md#tracking-uri`): they work on GitHub, and the app turns them into Help routes. Draw a diagram with a fenced ` ```mermaid ` block: GitHub renders it too, and the app draws it in the current theme with Mermaid (loaded only on pages that have one, strict security level, so no HTML labels or click handlers), showing the source and the parse error if it does not parse. `GuideMarkdown` renders them; the `Markdown` component is for user-written descriptions only. Help sits outside the signed-in pages in `router.tsx` and reads no `/api/v1` data, so it works signed out in server mode; `AppLayout` (the shell it shares with them) must not request session data on its own either. The one exception is the user opening the sidebar's Knowledge Graph switcher: that explicit action loads the Knowledge Graph list, so in server mode it may send a signed-out reader to sign-in.

## Testing

How to run each check, and what a green run prints, is in [`docs/agents/running-checks.md`](agents/running-checks.md).

### Python

- **`client` / `client_factory`** (`tests/conftest.py`) are parametrised over `tracking_mode`:
  - `local` uses a SQLite file;
  - `remote` runs the SDK against an in-process FastAPI `TestClient` backed by SQLite;
  - `postgres` is local mode over `$STETIQ_TEST_POSTGRES_URL`, with tables dropped per test, and is skipped when the variable is unset.

  Write each feature test once against `client`. `client_factory(**kw)` builds another client on the same data and forwards its kwargs to `Client`, e.g. `actor="ada"` or `graph_source=None`. In remote mode, each client gets a token with `{"*": "edit"}` for the user it resolves. Run a single mode with `uv run pytest -k remote`.
- **Raw HTTP tests** (`TestClient(create_app(url))`) must send a token. Issue one with `TokenRegistry(url).issue(user, grants)` and send it as `Authorization: Bearer …`, as `tests/test_server_trust.py` does.
- **The fake Graph Source.** The `graph_source` fixture is an `InMemoryGraphSource` shared by every client from the factory. Seed it in the test with `add_node`/`add_relationship`, and with `add_query_result` for executed Competency Questions. To change the graph between Observations, seed a second database and rebind the scope. CLI tests monkeypatch `stetiq.client.graph_source_from_env` to return the fake. An autouse fixture deletes `STETIQ_GRAPH_SOURCE_*`, so tests opt in with `monkeypatch.setenv`.
- **The Graph Source contract** lives in `tests/test_graph_source_contract.py` and runs over `memory` and `neo4j`. A new adapter behaviour must pass there unchanged, with literal expected values.
- **The stub question mapper.** Use `StubMapper` and the `mapped_client` fixture in `tests/test_use_cases.py`, which inject the mapper through `LocalTrackingService(…, question_mapper=)` or `create_app(…, question_mapper=)`. `Client` does not accept a mapper. LLM tests use the scripted `FakeAnthropic` in `tests/test_llm_mapping.py`. The `anthropic` package is the optional `llm` extra, and the test suite does not need it.
- **Postgres.** Use a container per agent, never a shared one, because `drop_all` runs per test:
  ```
  docker run -d --rm --name stetiq-pg-test -e POSTGRES_PASSWORD=stetiq -e POSTGRES_DB=stetiq_test -p 55432:5432 postgres:17
  STETIQ_TEST_POSTGRES_URL=postgresql+psycopg://postgres:stetiq@localhost:55432/stetiq_test uv run pytest
  ```
- **Neo4j.** Tests marked `neo4j` start a session-scoped testcontainer (`neo4j:2026.10-community`) whenever Docker answers, and skip cleanly when it does not. They are *not* deselected by default. Database scoping (a second database `other`) and the `reader`-role test need Enterprise: set `STETIQ_TEST_NEO4J_IMAGE=neo4j:2026.10-enterprise` (licence accepted in the fixture) to cover them; on Community the second-database seeding is a no-op and the role test skips. Run only these tests with `uv run pytest -m neo4j`.

### Frontend unit

- **Vitest** unit tests sit next to the module they test, as `*.test.ts` (e.g. `src/lib/data-table.test.ts`). They cover framework-free logic; anything that needs a browser goes in *End-to-end*.
- **Running them:** `npm run check` (`scripts/check.ts`), as in [`running-checks.md`](agents/running-checks.md).

### End-to-end

- **Playwright** specs live in `frontend/e2e/*.spec.ts` and use the harness in `frontend/e2e/fixtures.ts`.
- **Seeds.** A spec picks its data with `test.use({ seed: 'name' })`; `e2e/seed.py` runs that scenario against a local-mode `stetiq.Client` and the test gets its return value as `stetiq.seeded`. Scenarios live in the `frontend/e2e/seeds/` package, one module per feature area, each listing its scenarios in a `SCENARIOS` tuple. A new feature area gets its own module, added to `MODULES` in `seeds/__init__.py`; helpers and Ontologies shared by several modules go in `seeds/_shared.py` (`issue_token` for a `mode: 'server'` test). The package docstring has the full rules.
- **Running them:** which specs to run while building and before reporting is in [`running-checks.md`](agents/running-checks.md).
