"""Every example config on the stetiq.yaml guide page parses with the real loaders."""

import pytest
from guide_pages import code_blocks, read_page

from stetiq.config import load_config
from stetiq.drift import thresholds_from_config
from stetiq.entry_point import EntryPoint
from stetiq.gates import parse_gates
from stetiq.ontology import parse_yaml

EXAMPLES = [
    body
    for language, body in code_blocks(read_page("06-stetiq-yaml.md"))
    if language in {"yaml", "yml"}
]


def test_the_page_has_example_configs():
    assert len(EXAMPLES) >= 3


@pytest.mark.parametrize("example", EXAMPLES)
def test_example_config_parses_with_the_real_loaders(example, tmp_path):
    path = tmp_path / "stetiq.yaml"
    path.write_text(example, encoding="utf-8")

    config = load_config(path)

    if "knowledge_graph" in config:
        assert isinstance(config["knowledge_graph"], str) and config["knowledge_graph"]
    if "entry_point" in config:
        EntryPoint.from_config(config)
    thresholds_from_config(config)
    parse_gates(config.get("gates"))


def test_the_page_documents_cardinality_with_an_ontology_that_parses():
    (example,) = [body for body in EXAMPLES if "cardinality:" in body]

    (pattern,) = parse_yaml(example).patterns

    assert (pattern.min_out, pattern.max_out) == (1, 1)


def test_the_page_documents_vocabularies_with_an_ontology_that_parses():
    (example,) = [body for body in EXAMPLES if "vocabularies:" in body]

    ontology = parse_yaml(example)

    (status,) = ontology.vocabularies
    assert [v.label for v in status.values] == ["open", "in_review", "done", "closed"]
    assert {p.vocabulary for n in ontology.node_types for p in n.properties} == {"Status"}
