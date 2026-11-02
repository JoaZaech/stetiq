"""The pipeline's CD, standing in: replays a run's Extraction into the production graph.

The show deploys a run only after a Promotion (the `production` Contract Alias moved to
the version the run was built against), so the production graph only ever holds runs
stetiq let through.
"""

from __future__ import annotations

import neo4j

from plant_assistant.graph import Extraction, write

PRODUCTION_DATABASE = "neo4j"  # Neo4j Community has the one database


def deploy(
    production: neo4j.Driver, extraction: Extraction, *, database: str = PRODUCTION_DATABASE
) -> None:
    """Replace the production graph with `extraction`."""
    write(production, extraction, database=database)
