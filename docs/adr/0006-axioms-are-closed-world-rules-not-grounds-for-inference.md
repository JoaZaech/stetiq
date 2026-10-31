# Axioms are closed-world rules checked against the graph, not grounds for inference

In OWL and RDFS an Ontology is read open-world: a domain or range declaration does not reject data that breaks it, it infers a new type for that data, and a missing fact is unknown rather than false. Ontology engineering (for example Talisman, *Ontology Pipeline*, 2026) treats that inference as the ontology's main value and puts closed-world checking in a separate validation layer (SHACL) that has to be kept in step with the ontology. stetiq reads every Axiom closed-world instead. A subclass, a Relation's permitted endpoints and cardinality, a required Attribute, uniqueness and an Attribute's Vocabulary are all rules the graph must satisfy, and Conformance is the report of where it does not. stetiq never runs a reasoner and never derives facts. We chose this because the graphs stetiq governs are mostly property graphs, which are closed-world and have no reasoner. The core also never connects to a graph database (ADR 0005). Reading Axioms closed-world also means there is no second set of validation rules that can drift away from the Ontology. The Ontology is the validation rules.

## Consequences

- A user who brings an OWL ontology loses its inference semantics in stetiq. A domain declaration becomes a check, not a type assertion.
- Axiom kinds are added only when an Observation can check them. That is why cardinality is in, because the Observed Schema already records degrees, and disjointness is not, yet.
- Adding an Axiom, or tightening one, is a breaking Ontology Diff change, because existing graphs may stop conforming.
