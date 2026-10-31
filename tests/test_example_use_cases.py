"""Each example's `use-case.yaml` registers with its Consumers and Tasks in every tracking
mode. The example demos run over SQLite only; this covers the same Use Cases in
Postgres and server mode too."""

from pathlib import Path

import pytest

from stetiq.use_case import canonicalize, parse_use_case_yaml

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
USE_CASE_FILES = sorted(EXAMPLES.glob("*/use-case.yaml"))


def test_every_example_has_a_use_case():
    assert [f.parent.name for f in USE_CASE_FILES] == [
        "bookshelf-kg",
        "citation-graph-kg",
        "clinical-trials-kg",
        "plant-kg",
        "retail-orders-kg",
        "transit-network-kg",
    ]


@pytest.mark.parametrize("path", USE_CASE_FILES, ids=lambda p: p.parent.name)
def test_an_examples_use_case_keeps_its_consumers_and_tasks_once_registered(client_factory, path):
    declared = parse_use_case_yaml(path.read_text())
    assert declared.consumers and all(c.tasks for c in declared.consumers)

    # Each example starts from its first Ontology.
    first = "initial.yaml" if path.parent.name == "plant-kg" else "v1.yaml"
    client_factory().create_knowledge_graph(
        path.parent.name, ontology=path.parent / "ontology" / first
    )
    client_factory().register_use_case(path.parent.name, path)
    stored = client_factory().get_use_case_version(path.parent.name).use_case

    # Stored in canonical order (elements sorted by id), but otherwise as the file declares.
    assert stored == canonicalize(declared)
