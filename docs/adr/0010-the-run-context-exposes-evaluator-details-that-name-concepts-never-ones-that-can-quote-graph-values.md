---
status: accepted
---

# The Run Context exposes Evaluator details that name Concepts, never ones that can quote graph values

The Run Context is handed to LLM agents (the upstream pipeline's own extraction agent, and coding agents improving the pipeline through `stetiq mcp`), so whatever it carries may leave the user's control. It first carried Evaluator metrics only, because some details can quote values observed in the graph. But a metric alone is not actionable: an agent told `unjustified_additions: 2` cannot tell which Concepts it invented. So the Run Context includes the details of the built-in Evaluators that judge an Ontology Version (the version built-ins, `structural_answerability`, `competency_question_coverage` and `unjustified_additions`). They read only the Ontology and the Use Case, so their details name Concepts, Vocabulary Values and Competency Question ids and cannot hold a graph value. It never includes the details of run Evaluators that read the Graph Source (`conformance`, `observed_schema`) or of any custom Evaluator. Executed Competency Questions keep appearing as a status and a row count. This extends ADR 0001: what reaches an agent is structure, never instance data.

## Considered Options

- **Metrics only, as before.** Rejected: agents can see that something is wrong but not what, so the loop from evaluation back to extraction doesn't close.
- **All details, with values scrubbed.** Rejected: custom Evaluators' details are free-form, so no scrubber can promise they hold no instance data.
- **Let the user opt Evaluators in.** Rejected for now: one switch turns the no-instance-data promise into a per-deployment setting that nobody audits.

## Consequences

- The line is drawn by what an Evaluator reads, not by name: a new built-in that judges an Ontology Version from the Ontology and Use Case alone is exposed, and one that reads the Graph Source is not.
- Conformance mismatches stay out even though they would help an agent. The agent learns about them from the Conformance metric and from the Gate verdict, and a person reads the details in the web UI.
- A strict-failed attempt's Ontology Diff (the Run Context's `last_attempt`) leaves out the Vocabulary Values its never-registered Candidate would have added, for the same reason: they are values observed in the graph that never became Ontology. Only their count is shown. An evolving run's added values are kept, because its registered Candidate made them Ontology.
