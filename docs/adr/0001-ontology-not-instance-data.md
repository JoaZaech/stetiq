# stetiq governs ontology structure, never instance data

stetiq versions, diffs, evaluates and promotes a knowledge graph's Ontology; it does not snapshot, diff, identify or load instance data. The Graph Source is read only to derive the Observed Schema, which includes aggregate structural statistics (counts per class and relation, cardinalities, attribute fill rates) but never individual entities. Most "MLflow for knowledge graphs" designs version graph snapshots and need triple-level diffs, stable entity IDs and data deployment; we deliberately leave that to the graph database and tools like TerminusDB, and make the Ontology Version the only artifact stetiq owns. "Deploying" an Ontology Version therefore means pointing the Contract Alias at it, which extraction pipelines and Drift detection consume as the contract, not loading data.

## Consequences

- stetiq never writes to a Graph Source (no constraint enforcement, no blue/green data loads).
- A drop in instance volume with an unchanged ontology still surfaces, as Drift on the Observed Schema's statistics.
- The one place Observation reads instance values is a Vocabulary-bound Attribute: it records the distinct values that Attribute takes, with counts, up to a cap. A Vocabulary is part of the Ontology, so the values it permits are structure, and without them a Vocabulary could not be checked.
- stetiq borrows MLflow's concepts but neither depends on nor integrates with MLflow.
