---
status: accepted
---

# Drift compares rates with a post-Promotion Baseline Observation, Axiom checks are Violation Rates, and a Drift exit means new findings

Drift used to compare an Observation with the contract (structure) and with the previous Observation (counts). That misses a graph that decays slowly: a required Attribute losing 2% of its fill each week never moves far enough between two Observations to trip a threshold, and the Axiom checks a Construction Run's Conformance makes (`required_missing`, `type_mismatch`, `cardinality_violation`) never alerted between runs at all. So Axiom checks become **Violation Rates**, the share of owner nodes or relationships that fail a Conformance check, carried on the Conformance `Mismatch` itself, so runs, Observations and future Gates read one engine. Drift raises `violation_increase` when a Violation Rate is more than `max_violation_increase` absolute points (default 0.01, `null` turns it off) above its value in the **Baseline Observation**: the first Observation, run-end ones included, since the Contract Alias's current Ontology Version became the contract, by a Promotion or by switching the Contract Alias. Ratios compare with the baseline, counts keep comparing with the previous Observation. Drift asks "did it get worse since we accepted this contract?"; "is it good enough?" stays a Gate's question. A check that lacks its input (a rate the baseline cannot give, a truncated value list) never raises a finding: the Observation records it as *not comparable*. Each finding is *new*, or *persisting* when the previous Observation had it too and, for a rate, it has not moved further from its baseline value since; `stetiq observe` exits 3 only when at least one finding is new, so a scheduled job alerts once per change instead of on every Observation while a known gap stays as it is.

## Considered Options

- **Any non-zero Violation Rate as Drift**, whatever the baseline had. Rejected: a graph that has always had 0.5% of Customers without a name would alert on every Observation, and the scheduled job gets muted.
- **Compare rates with the previous Observation.** Rejected: slow decay never trips the threshold, which is the problem being solved.
- **Compare counts with the baseline too.** Rejected: a growing graph eventually trips any cumulative count threshold.
- **A baseline the user pins.** Rejected for now: a pinned baseline outlives the contract it was taken under. A Promotion or a switch of the Contract Alias is the moment the team accepted a structure, so it starts the comparison.
- **A relative threshold on rates** (e.g. 10% worse). Rejected: from a 0% baseline any rise is infinitely worse, and 0.1% → 0.2% is a doubling nobody acts on. Absolute points read the same at every level.
- **Exit 3 on every finding**, new or not. Rejected: the same reason, a known gap alerting on every Observation; `--fail-on-persisting` keeps that behaviour for whoever wants it.
- **Rates outside Conformance**, computed by Drift alone. Rejected: Conformance and Drift would disagree about the same check, and a future Gate on rates would need a third copy.

## Consequences

- `Mismatch` gains an optional `rate`, and the Conformance score is unchanged (one binary item per check), so existing `conformance` Gates behave as before.
- Each on-demand Observation stores its `baseline_observation_id` (its own id when it is the first since the contract changed, so there is no rate Drift yet) and its not-comparable checks. Switching the Contract Alias records when, which a Promotion already did.
- `max_violation_increase` is on by default, so upgrading turns the check on for everyone, at one percentage point. Drift events store the threshold in effect; events written before the check existed read as having had it off.
- `undeclared_value` findings carry their count and share of the owner. A truncated value list (more distinct values than the cap) still raises `undeclared_value` for each listed value outside the Vocabulary, since structural Drift is always on, but never a rate finding: the share is unknown, so the check is reported as not comparable. This is deliberate: a value the contract lacks is Drift however many others the cap left out.
- A Drift finding's subject can be a pattern, which the cardinality Violation Rate needs.
- Later slices add the `type_mismatch` and `cardinality_violation` rates, Coverage, fill rates and `min_count` to the same baseline comparison, and mark findings *new* or *persisting* so that `stetiq observe` exits 3 only on new ones (`--fail-on-persisting` exits 3 on any finding).
