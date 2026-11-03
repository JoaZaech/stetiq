---
status: accepted
---

# Every visualization in the web UI is drawn with d3.js

Every visualization in stetiq (a chart, a plot, a node-link view such as the Ontology Map, or any other drawing of data) is built with d3.js. This replaces the Recharts choice in ADR 0003; the rest of ADR 0003 stands.

## Consequences

- A new visualization uses d3 (the `d3` package or its `d3-*` modules) for its scales, shapes, axes, layouts and interaction. It does not add Recharts, React Flow, or another charting or graph-drawing library.
- The rule is enforced by lint: `no-restricted-imports` in `frontend/eslint.config.js` makes importing any other charting or graph-drawing library an error, so `npm run check` fails.
- Existing visualizations not yet on d3 are to be moved to it: `MetricChartGrid` (Recharts) and the Ontology Map, which the Comparison Map reuses (`@xyflow/react` with `elkjs`). Their three files are the only exceptions in the lint config. No file is added to that list; each is removed when it is migrated.
- The Style rules in `docs/architecture.md` (tokens only, status tokens for status marks) apply to d3 drawings too: colours come from tokens via `var(--…)`, never from d3's built-in colour schemes.
