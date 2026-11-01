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

## User guide

`docs/guide/` is the user guide, rendered in the web UI at `/ui/help` (ADR 0004). A change to what users see or do (an SDK call, CLI command, REST route, `stetiq.yaml` key, or anything in the web UI) updates the guide page that describes it in the same branch. The guide describes what has shipped, in the words the UI uses; internal renames and refactors leave it alone.
