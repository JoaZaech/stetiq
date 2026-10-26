# stetiq

## How we work with agents

This repo uses [Matt Pocock's skills](https://github.com/mattpocock/skills) for Claude Code. Their settings live in `docs/agents/`. Issues go in GitHub Issues, and the triage labels are `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` and `wontfix`.

### From idea to pull request

```
/grill-with-docs <idea>      ┐
/to-spec                     │ one session: no /clear or /compact until the tickets are published
/to-tickets #<spec-issue>    ┘
/implement #<ticket>         ← one ticket per session, /clear between them
  …or /implement-spec #<spec-issue> for the whole spec in one run
Pull request                 ← /pr writes the body
/retro                       ← same session, before you clear
```

You type each of these commands yourself. The agent won't start them on its own.

#### 1. Grill: `/grill-with-docs <idea>`

The agent asks you questions about the idea until every open question has an answer. As terms and decisions get settled, it writes them down in `GLOSSARY.md` and `docs/adr/`.

If a question can only be answered by running code (how the state should work, the business rules, what a UI looks like), take a detour:

1. Run `/handoff`, then open a fresh session.
2. Answer the question there with `/prototype`.
3. Run `/handoff` again to bring what you learned back to the original session.

#### 2. Spec: `/to-spec`

This step asks no new questions. The agent turns the conversation into a spec and checks with you where the tests will hook into the code. Then it posts the spec as a GitHub issue labelled `ready-for-agent`.

#### 3. Tickets: `/to-tickets #<spec-issue>`

The agent proposes small tickets. Each one builds a thin piece of the feature end to end, and each lists the tickets that must be finished before it can start. You approve how big they are and what depends on what. The agent then posts one issue per ticket, the tickets that block others first, linked with GitHub's "blocked by" relationship. Passing the spec's issue number makes the tickets sub-issues of the spec.

Don't run `/triage` on these tickets. They're ready to build as they are.

> **Keep steps 1–3 in one session.** Don't `/clear` or `/compact` until the tickets are published, so the spec and tickets come from the same conversation as the grilling. If the session gets very long (around 150k tokens), `/compact` between two steps rather than pushing on.

#### 4. Build

Choose one of these:

- **`/implement #<ticket>`**, one ticket at a time, with `/clear` between tickets. The agent writes tests first (`/tdd`), reviews its own work (`/code-review`) and **commits to the current branch**. It doesn't create a branch or open a pull request, so check out a feature branch first and ask for the PR when it's done. Start with any ticket that isn't blocked.
- **`/implement-spec #<spec-issue>`** builds the whole spec in one run. Several agents work on the unblocked tickets at once, their work is merged onto one integration branch, and one `/code-review` runs at the end. It opens a draft PR only if you ask, so add "and open a PR" to the command.

#### 5. Pull request

When the agent writes a PR body, the `/pr` skill sets the format: a small diagram or tree of the change, before/after evidence that it works, and a note on whether the change is easy to undo. Add `Closes #<ticket>` to the body so merging the PR closes the ticket.

#### 6. Retro: `/retro`

Run this in the same session, before you clear it. It looks back over the session and suggests improvements to the setup, such as new checks, coding standards or notes for the agent. It doesn't change the code.

### Shortcuts

- **Small change:** skip the spec and tickets. Run `/grill-with-docs`, then `/implement` in the same session.
- **Large project that isn't clear yet:** start with `/wayfinder` instead of grilling. It works through the open decisions as GitHub issues, then joins this flow at `/to-spec`.
- **Bug reports and requests from other people:** run `/triage` on them to label them and make them ready to build, then build them with `/implement`.
- **A bug that's hard to track down:** use `/diagnosing-bugs`.
