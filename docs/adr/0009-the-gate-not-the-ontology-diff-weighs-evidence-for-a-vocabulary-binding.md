# The Gate, not the Ontology Diff, weighs observed evidence for a Vocabulary binding

Binding an Attribute to a Vocabulary (from none, or from another Vocabulary) is classed **breaking** in the Ontology Diff, because a binding may reject values the graph already holds. An `ontology_diff` Gate nonetheless accepts the binding when the gated run's Observed Schema lists that Attribute's values, the list isn't truncated, and every value is a Value of the new Vocabulary; it then adds a reason saying so. No Observation, unobserved values, a truncated list or any value outside the Vocabulary leaves the binding breaking, so a missing input is never a pass. The rule is always on, with no `stetiq.yaml` key. We put the evidence in the Gate because the Ontology Diff compares two artifacts, two Ontology Versions, and Consumer impact, the Diff view and the Connector payload all read it: mixing Observation statistics into it would change what a Diff is, and the same two versions would diff differently depending on which run looked at the graph. The Gate already receives the subject's Observed Schema and is where verdicts are made. Reading the values relies on ADR 0001's Vocabulary exception. This departs from the map's lean in #146, which was to class the binding as additive in the Diff.

## Considered Options

- **Classify the binding as additive in the Ontology Diff when the data satisfies it.** Rejected: the Diff would depend on an Observation, Consumer impact and the Diff view would stop showing that the binding can reject values, and a later run with an outside value would silently turn a recorded additive change breaking.
- **A Gate override or a declared migration.** Rejected for now: it waves a breaking change through on someone's word, where the evidence rule only passes what the data already proves.

## Consequences

- The Diff, the Diff view, Consumer impact and the Connector payload keep classing the binding as breaking beside a green Gate; the Gate's reason explains the green.
- A binding alongside another breaking change still fails the Gate: the evidence excuses only the binding.
- A run in evolving mode that observes an outside value yields a Candidate whose Vocabulary takes the value in; the Gate judges the binding against that Candidate's Vocabulary, and the run's Conformance still reports the value.
