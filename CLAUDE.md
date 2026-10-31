## Agent skills

### Issue tracker

Issues live in GitHub Issues for `JoaZaech/stetiq`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Running checks

Run checks and tests as `docs/agents/running-checks.md` describes.

## Architecture

Before adding an SDK operation, REST route, CLI command or test fixture, read `docs/architecture.md`. A brief for a subagent cites the one section it needs (e.g. *Frontend › Map*), not the whole file.
