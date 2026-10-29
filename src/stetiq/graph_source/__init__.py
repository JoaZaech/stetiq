"""Graph Source adapter: the read-only seam between stetiq and an external graph database.

`GraphSource` is the interface (`observe(scope) -> ObservedSchema`, `execute_read(...)`);
`InMemoryGraphSource` is the fake used in tests; `Neo4jGraphSource` is the real, read-only
adapter. Both pass the shared contract suite (tests/test_graph_source_contract.py).
"""

from stetiq.graph_source.memory import InMemoryGraphSource
from stetiq.graph_source.model import (
    NAMESPACE_PROPERTY,
    Degree,
    GraphSourceScope,
    ObservedNodeType,
    ObservedPattern,
    ObservedProperty,
    ObservedRelationshipType,
    ObservedSchema,
)
from stetiq.graph_source.neo4j import Neo4jGraphSource, graph_source_from_env
from stetiq.graph_source.protocol import GraphSource

__all__ = [
    "NAMESPACE_PROPERTY",
    "Degree",
    "GraphSource",
    "GraphSourceScope",
    "InMemoryGraphSource",
    "Neo4jGraphSource",
    "ObservedNodeType",
    "ObservedPattern",
    "ObservedProperty",
    "ObservedRelationshipType",
    "ObservedSchema",
    "graph_source_from_env",
]
