# The Ontology is a versioned contract between the upstream pipeline and its Consumers

stetiq keeps a Knowledge Graph's Ontology as a contract with two sides of equal standing. The upstream pipeline's side is the Ontology Version it builds to. The Consumers' side is the Use Case, where each Consumer declares its Tasks and the Competency Questions they need answered. Both are versioned independently, and every proposed change is checked against each: Gates and Conformance for what the pipeline produces, Consumer impact and Consumer Gates for what each Consumer would lose. The question stetiq answers is "can this Ontology change ship without breaking either side?", and it succeeds on two criteria together: no change reaches a declared Consumer and breaks a Task it relies on unless someone saw and accepted that before Promotion, and the pipeline can make any change no declared Consumer depends on with only its own Gates to pass. stetiq referees the contract and never writes it: Candidates come from the pipeline or a person, and AI drafting and Adoption only propose. It protects only what Consumers declare, and it governs structure only (ADR 0001). This replaces the earlier framing of stetiq as "the evaluation point" that judges the input side first, "the way MLflow does for models", which made the Consumer side a later addition when the Consumer Gate is what sets stetiq apart.

## Considered Options

- **A one-sided evaluation point, "MLflow for knowledge graph structure".** Replaced: a model registry answers to whoever trains the model, and its framing hid the Consumer side behind the input side. The registry ideas (versions, Aliases, Promotion) stay.
- **An optimizer that searches for or proposes the Ontology that best serves both sides.** Rejected: stetiq has no objective function to optimise, and authoring the Ontology would pull it into extraction, which stays the user's. stetiq makes the trade-off visible and enforceable; people make it.

## Consequences

- The first success criterion is an aim the code does not yet fully meet: the Promote dialog shows Consumer impact, but the Promotion audit records only the target version's latest Gate result, not the Consumer impact or Consumer Gate verdicts the promoter saw. "Accepted" is therefore not yet recorded.
- A Consumer that is not declared in the Use Case, or whose Competency Questions are neither mapped nor given a query, is not protected; its impact is unknown, never reported as unaffected.
- The contract must not freeze the pipeline: a change no declared Consumer depends on faces only the pipeline's own Gates.
