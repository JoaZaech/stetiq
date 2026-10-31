# Gate Previews are computed on demand and never recorded

Comparing Construction Runs means judging each KPI (run metrics, Evaluator results and Conformance) as good or bad, and the user already says what good means with Gates. But a Gate result exists only for a subject CI gated, and the Gates themselves live in the user's `stetiq.yaml`, which the server never reads. So stetiq judges ungated runs with a Gate Preview: the server evaluates the Gate definitions of the most recent Gate result about a Construction Run (else about any subject) against the run, on demand, and returns the outcome without storing it. A recorded Gate result about the subject always wins over a preview. We never record previews because a recorded Gate result is what Promotion's audit trusts as "CI checked this with the repo's Gates". A result computed from Gates the server merely remembers, against a run CI never looked at, would claim more than it knows.

## Considered Options

- **Record a Gate result at the end of every run.** Rejected: the server does not hold the current Gate definitions, and recorded results would mix CI's verdicts with the server's guesses in the audit.
- **Leave ungated runs neutral.** Rejected: most runs are created outside CI, so the comparison would show almost no verdicts.

## Consequences

- A preview can disagree with what CI would decide today, if the repo's Gates changed since the last recorded result. The UI labels previews "judged against current Gates" and names the Gate result their definitions came from.
- Previews are pure reads, so they need only *read* permission, and computing them has no side effects.
