"""The registry's own Evaluators, registered on the stetiq Client.

They run in this process (the SDK side); only their metrics and details reach the
tracking service. Both are named by Gates in stetiq.yaml.
"""

from __future__ import annotations

from trials_graph import PARTICIPANT_COUNT, PARTICIPANTS_WITHOUT_CONSENT

from stetiq import ConstructionRunEvaluator, Detail, Evaluation, OntologyVersionEvaluator
from stetiq.evaluation.framework import ratio

# Property names that would turn a pseudonymous participant into an identifiable person.
PII_PROPERTY_NAMES = frozenset({"name", "email", "dob", "date_of_birth", "address", "phone"})
PSEUDONYMOUS_NODE_TYPE = "Participant"


class PiiFree(OntologyVersionEvaluator):
    """The Ontology must leave no room for personal data on a Participant.

    The registry only ever holds pseudonyms, so an Ontology Version that declares a
    `name`, `email`, `dob`, `address` or `phone` property on Participant (or on a
    subtype of it) is wrong before any data is loaded. Metric `pii_properties`, one
    Detail per offending property. A pure function of the Ontology: no graph access.
    """

    name = "pii_free"

    def evaluate(self, version) -> Evaluation:
        ontology = version.ontology
        subtypes = {PSEUDONYMOUS_NODE_TYPE}
        for node_type in ontology.node_types:  # single inheritance, declared in any order
            if node_type.parent in subtypes:
                subtypes.add(node_type.label)
        offending = [
            f"{n.label}.{p.name}"
            for n in ontology.node_types
            if n.label in subtypes
            for p in n.properties
            if p.name.lower() in PII_PROPERTY_NAMES
        ]
        return Evaluation(
            metrics={"pii_properties": len(offending)},
            details=[
                Detail(item=item, message="personal data has no place on a pseudonymous node type")
                for item in offending
            ],
        )


class ConsentCoverage(ConstructionRunEvaluator):
    """Does every participant in the graph have a recorded consent?

    A participant row comes from participants.csv, the CONSENTED_TO relationship from
    consent.csv. A participant without one must not be in a regulated registry graph
    at all. Counts only (ADR 0001): the two queries return aggregates and no pseudonym
    leaves the Graph Source.
    """

    name = "consent_coverage"

    def evaluate(self, run) -> Evaluation:
        [total] = run.graph_source.execute_read(PARTICIPANT_COUNT)
        [missing] = run.graph_source.execute_read(PARTICIPANTS_WITHOUT_CONSENT)
        participants, without = total["participants"], missing["participants"]
        return Evaluation(
            metrics={
                "participants": participants,
                "without_consent": without,
                "coverage": ratio(participants - without, participants),
            }
        )
