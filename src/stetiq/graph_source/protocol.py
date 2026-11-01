"""The Graph Source adapter interface."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any, Protocol

from stetiq.graph_source.model import (
    DEFAULT_VALUE_CAP,
    BoundAttribute,
    GraphSourceScope,
    ObservedSchema,
)


class GraphSource(Protocol):
    """Read-only access to an external graph database. Never writes, and never hands
    individual entities to stetiq's store (ADR 0001)."""

    def observe(
        self,
        scope: GraphSourceScope,
        bound_attributes: Collection[BoundAttribute] = (),
        *,
        value_cap: int = DEFAULT_VALUE_CAP,
    ) -> ObservedSchema:
        """The Observed Schema of everything inside `scope`, with aggregate statistics.

        For each of `bound_attributes` (the Vocabulary-bound Attributes) that the graph
        holds, its `ObservedProperty.values` gives the distinct string values with
        counts, at most `value_cap` of them. No other instance value is read."""
        ...

    def execute_read(
        self, scope: GraphSourceScope, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Run a read-only query against `scope.database` (executed Competency Questions
        only). Results are evaluated and discarded, never stored."""
        ...
