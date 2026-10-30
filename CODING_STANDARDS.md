# Coding standards

Judgement calls for reviewers. Anything mechanical is enforced by ruff and pyright (see `.github/workflows/ci.yml`), not here.

## The server is the authority

The server computes or derives every verdict and every provenance field: Gate outcomes, an Ontology Version's origin, which version is a Candidate, the actor in the audit log. A client sends inputs (an Ontology, Gate definitions, an Observation), never outcomes. A REST body field that lets a client state a result the server could compute is a defect, even when today's SDK fills it honestly.

The exceptions are what has to run where the Graph Source and the user's code live, in the SDK process: Observations, custom Evaluators, and executed Competency Questions. Their results are stored as reported, under names the server reserves for them.

## Reuse before adding

Before writing a helper, search for one that already renders, hashes, compares or serialises the same thing (`Pattern.__str__`, `stetiq.digest`, `evaluation.framework.ratio`, `Degree.to_dict`). A second copy of an existing shape is a finding, even if the two copies sit in different modules.

## Structure, never instance data

Nothing stetiq stores may contain an individual node, relationship, property value or query row (ADR 0001). That includes error messages from the Graph Source, which can quote instance values; store the exception type instead.

## One meaning per type alias

A `Literal` alias names exactly one domain concept. Reuse `SubjectKind` (what an evaluation or Gate is about) and `ConceptKind` (class, relation, attribute) instead of declaring a look-alike.

## Domain vocabulary

Names, messages and docstrings use GLOSSARY.md terms. A word listed under _Avoid_ is a finding wherever it refers to that concept.
