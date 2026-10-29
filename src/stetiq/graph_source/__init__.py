"""Graph Source adapter: the read-only seam between stetiq and an external graph database.

`GraphSource` is the interface (`observe(scope) -> ObservedSchema`, `execute_read(...)`);
`InMemoryGraphSource` is the fake used in tests. The Neo4j adapter implements the same
interface and must pass the shared contract suite (tests/test_graph_source_contract.py).
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
from stetiq.graph_source.protocol import GraphSource

__all__ = [
    "NAMESPACE_PROPERTY",
    "Degree",
    "GraphSource",
    "GraphSourceScope",
    "InMemoryGraphSource",
    "ObservedNodeType",
    "ObservedPattern",
    "ObservedProperty",
    "ObservedRelationshipType",
    "ObservedSchema",
]
